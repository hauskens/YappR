use sea_orm::{ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter};
use serenity::all::{
    ChannelId, Client, Context, EventHandler, GatewayIntents, Interaction, Message, MessageId,
    Reaction, Ready,
};
use serenity::async_trait;
use std::collections::HashSet;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{error, info, warn};
use yappr_bot::discord::{
    commands::CommandHandler, message_handler::MessageHandler, moderation::DiscordMessageDeletion,
    reactions::ReactionHandler,
};
use yappr_bot::services::BotUserService;
use yappr_shared::config::Config;
use yappr_shared::database::get_database_connection;
use yappr_shared::entities::{channel_settings, channels, prelude::*};
use yappr_shared::models::channel::ChannelSettings;
use yappr_shared::models::platforms::AccountPlatform;

#[tokio::main]
async fn main() -> Result<(), eyre::Report> {
    // Set up logging
    tracing_subscriber::fmt::fmt()
        .with_writer(std::io::stderr)
        .init();

    info!("Starting Discord bot...");

    // Get database connection
    let db = get_database_connection().await?;
    info!("Database connection established");

    // Load configuration
    let config = Config::load();

    // Get Discord bot token from environment
    let token =
        std::env::var("DISCORD_BOT_TOKEN").expect("DISCORD_BOT_TOKEN environment variable not set");

    let bot = Bot { db, config };

    bot.start(token).await?;
    Ok(())
}

pub struct Bot {
    pub db: DatabaseConnection,
    pub config: Config,
}

impl Bot {
    pub async fn start(self, token: String) -> Result<(), eyre::Report> {
        // Initialize services
        let chatlog_service = Arc::new(yappr_bot::services::ChatlogService::new(self.db.clone()));
        let user_service = Arc::new(BotUserService::new(
            self.db.clone(),
            AccountPlatform::Discord,
        ));
        let reaction_handler = Arc::new(ReactionHandler::new(self.db.clone()));
        let active_listening_channels = Arc::new(RwLock::new(HashSet::new()));
        let command_handler = Arc::new(CommandHandler::new(
            self.db.clone(),
            active_listening_channels.clone(),
        ));
        let message_handler = Arc::new(MessageHandler::new(
            self.db.clone(),
            chatlog_service.clone(),
            user_service.clone(),
        ));

        info!("Services initialized");

        // Load verified channels
        command_handler.load_verified_channels().await?;

        // Create event handler
        let handler = DiscordEventHandler {
            db: self.db.clone(),
            config: self.config.clone(),
            reaction_handler,
            command_handler,
            message_handler,
            active_listening_channels,
        };

        // Set up intents
        let intents = GatewayIntents::GUILDS
            | GatewayIntents::GUILD_MESSAGES
            | GatewayIntents::GUILD_MESSAGE_REACTIONS
            | GatewayIntents::MESSAGE_CONTENT;

        // Create client
        let mut client = Client::builder(token, intents)
            .event_handler(handler)
            .await?;

        info!("Discord client initialized");

        // Start the client
        client.start().await?;

        info!("Bot shut down gracefully");
        Ok(())
    }
}

struct DiscordEventHandler {
    db: DatabaseConnection,
    config: Config,
    reaction_handler: Arc<ReactionHandler>,
    command_handler: Arc<CommandHandler>,
    message_handler: Arc<MessageHandler>,
    active_listening_channels: Arc<RwLock<HashSet<u64>>>,
}

#[async_trait]
impl EventHandler for DiscordEventHandler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        info!("Bot logged in as {}", ready.user.name);

        // Register slash commands
        if self.config.debug {
            // In debug mode, don't register commands
            info!("Debug mode: Not registering slash commands");
        } else {
            // Register commands globally
            match ctx
                .http
                .create_global_commands(&CommandHandler::register_commands())
                .await
            {
                Ok(_) => info!("Registered global slash commands"),
                Err(e) => error!(error = %e, "Failed to register commands"),
            }
        }

        info!("Discord bot is ready!");
    }

    async fn message(&self, _ctx: Context, msg: Message) {
        // Ignore bot messages
        if msg.author.bot {
            return;
        }

        let channel_id = msg.channel_id.get();

        // Check if in active listening channel
        let is_listening = {
            let channels = self.active_listening_channels.read().await;
            channels.contains(&channel_id)
        };

        if !is_listening {
            return;
        }

        info!(
            user = %msg.author.name,
            channel_id = channel_id,
            "Processing message in listening channel"
        );

        // Clone all the Arc references we need for the spawned task
        let command_handler = self.command_handler.clone();
        let message_handler = self.message_handler.clone();
        let reaction_handler = self.reaction_handler.clone();
        let db = self.db.clone();
        let message_id = msg.id.get();
        let content = msg.content.clone();

        // Spawn task to handle message processing
        tokio::spawn(async move {
            // Get broadcaster settings for this channel
            let broadcaster_id = match command_handler
                .get_broadcaster_for_channel(channel_id)
                .await
            {
                Ok(Some(id)) => id,
                Ok(None) => {
                    warn!(channel_id = channel_id, "No broadcaster found for channel");
                    return;
                }
                Err(e) => {
                    error!(error = %e, channel_id = channel_id, "Failed to get broadcaster for channel");
                    return;
                }
            };

            // Get channel settings for this broadcaster
            let settings = match get_channel_settings_for_broadcaster(&db, broadcaster_id).await {
                Ok(Some(settings)) => settings,
                Ok(None) => {
                    warn!(broadcaster_id = broadcaster_id, "No channel settings found");
                    return;
                }
                Err(e) => {
                    error!(error = %e, broadcaster_id = broadcaster_id, "Failed to get channel settings");
                    return;
                }
            };

            // Handle message
            if let Err(e) = message_handler.handle_message(msg, &settings).await {
                error!(error = %e, "Failed to handle message");
            }

            // Track message for reactions if content queue is enabled
            if settings.content_queue_enabled {
                // Check if message contains URLs (simplified check)
                if content.contains("http://") || content.contains("https://") {
                    reaction_handler.track_message(message_id).await;
                }
            }
        });
    }

    async fn message_delete(
        &self,
        _ctx: Context,
        channel_id: ChannelId,
        deleted_message_id: MessageId,
        _guild_id: Option<serenity::all::GuildId>,
    ) {
        info!(
            message_id = deleted_message_id.get(),
            channel_id = channel_id.get(),
            "Message deleted"
        );

        // Untrack the message
        self.reaction_handler
            .untrack_message(deleted_message_id.get())
            .await;

        // Handle deletion (clean up content queue)
        if let Err(e) = DiscordMessageDeletion::handle(&self.db, deleted_message_id.get()).await {
            error!(error = %e, "Failed to handle message deletion");
        }
    }

    async fn reaction_add(&self, ctx: Context, reaction: Reaction) {
        let message_id = reaction.message_id.get();

        // Check if we're tracking this message
        if !self.reaction_handler.is_tracked(message_id).await {
            return;
        }

        info!(
            message_id = message_id,
            user_id = ?reaction.user_id,
            "Reaction added"
        );

        // Schedule debounced vote update
        self.reaction_handler.schedule_vote_update(message_id).await;

        // Count votes immediately (without debouncing for now)
        // In production, you might want to debounce this more aggressively
        if let Err(e) = self
            .reaction_handler
            .count_and_update_votes(&ctx, reaction.channel_id, reaction.message_id)
            .await
        {
            error!(error = %e, "Failed to count votes");
        }
    }

    async fn reaction_remove(&self, ctx: Context, reaction: Reaction) {
        let message_id = reaction.message_id.get();

        // Check if we're tracking this message
        if !self.reaction_handler.is_tracked(message_id).await {
            return;
        }

        info!(
            message_id = message_id,
            user_id = ?reaction.user_id,
            "Reaction removed"
        );

        // Schedule debounced vote update
        self.reaction_handler.schedule_vote_update(message_id).await;

        // Count votes
        if let Err(e) = self
            .reaction_handler
            .count_and_update_votes(&ctx, reaction.channel_id, reaction.message_id)
            .await
        {
            error!(error = %e, "Failed to count votes");
        }
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        if let Interaction::Command(command) = interaction {
            info!(command = %command.data.name, "Processing command");

            if let Err(e) = self.command_handler.handle_command(&ctx, &command).await {
                error!(error = %e, command = %command.data.name, "Failed to handle command");
            }
        }
    }
}

/// Helper function to get channel settings for a broadcaster
async fn get_channel_settings_for_broadcaster(
    db: &DatabaseConnection,
    broadcaster_id: i32,
) -> Result<Option<ChannelSettings>, eyre::Report> {
    // Get the first channel for this broadcaster (Discord broadcasters typically have one channel)
    let channel_with_settings = Channels::find()
        .find_also_related(channel_settings::Entity)
        .filter(channels::Column::BroadcasterId.eq(broadcaster_id))
        .one(db)
        .await?;

    match channel_with_settings {
        Some((channel, Some(settings))) => Ok(Some(ChannelSettings {
            channel_id: channel.id,
            broadcaster_id: channel.broadcaster_id,
            content_queue_enabled: settings.content_queue_enabled,
            chat_collection_enabled: settings.chat_collection_enabled,
        })),
        _ => Ok(None),
    }
}
