use std::sync::Arc;
use tracing::{error, info};
use twitch_api::{HelixClient, client::ClientDefault};
use twitch_oauth2::UserToken;
use yappr_bot::services::{BotUserService, ChatlogService};
use yappr_bot::twitch::{
    auth, channel_manager::ChannelManager, message_handler::MessageHandler,
    moderation_handler::ModerationHandler, websocket,
};
use yappr_shared::config::Config;
use yappr_shared::database::get_database_connection;
use yappr_shared::logging;
use yappr_shared::models::platforms::AccountPlatform;

#[tokio::main]
async fn main() -> Result<(), eyre::Report> {
    // Load configuration
    let config = Config::load();

    // Initialize logging with shared configuration
    logging::init_logging(
        "twitch-bot",
        config.loki_url.value.clone(),
        config.version.value.clone(),
        config.environment.value.clone(),
    );

    info!("Starting Twitch bot...");

    // Get database connection
    let db = get_database_connection().await?;
    info!("Database connection established");

    // Get bot token
    let token = auth::get_user_token().await?;
    info!("Bot authentication successful");

    // Create Twitch API client
    let client: HelixClient<'static, reqwest::Client> = twitch_api::HelixClient::with_client(
        ClientDefault::default_client_with_name(Some("yappr_bot".parse()?))?,
    );

    let bot = Bot {
        db,
        client,
        token,
        config,
    };

    bot.start().await?;
    Ok(())
}

pub struct Bot {
    pub db: sea_orm::DatabaseConnection,
    pub client: HelixClient<'static, reqwest::Client>,
    pub token: UserToken,
    pub config: Config,
}

impl Bot {
    pub async fn start(self) -> Result<(), eyre::Report> {
        let chatlog_service = Arc::new(ChatlogService::new(self.db.clone()));
        let user_service = Arc::new(BotUserService::new(
            self.db.clone(),
            AccountPlatform::Twitch,
        ));
        let channel_manager = Arc::new(ChannelManager::new(self.db.clone()));
        let message_handler = Arc::new(MessageHandler::new(
            self.db.clone(),
            chatlog_service.clone(),
            user_service.clone(),
        ));
        let moderation_handler = Arc::new(ModerationHandler::new(self.db.clone()));

        info!("Services initialized");

        // Start background tasks
        let chatlog_task = {
            let service = chatlog_service.clone();
            tokio::spawn(async move {
                service.start_periodic_commit().await;
            })
        };

        let channel_refresh_task = {
            let manager = channel_manager.clone();
            tokio::spawn(async move {
                if let Err(e) = manager.start_periodic_refresh().await {
                    error!(error = %e, "Channel refresh task failed");
                }
            })
        };

        info!("Background tasks started");

        // Create websocket client
        let websocket_client = websocket::WebsocketClient {
            session_id: None,
            token: self.token.clone(),
            client: self.client.clone(),
            connect_url: twitch_api::TWITCH_EVENTSUB_WEBSOCKET_URL.clone(),
            subscribed_channels: Vec::new(),
            bot_user_id: self
                .config
                .bot_user_id
                .value
                .clone()
                .expect("Unable to load bot user id from config"),
            channel_manager,
            message_handler,
            moderation_handler,
            consecutive_failures: 0,
            current_backoff: std::time::Duration::from_secs(1),
        };

        info!("Starting websocket client...");

        // Run websocket client in a select with background tasks
        tokio::select! {
            result = websocket_client.run() => {
                match result {
                    Ok(_) => info!("Websocket client exited gracefully"),
                    Err(e) => {
                        error!(error = %e, "Websocket client terminated with unrecoverable error");
                        error!("This typically indicates an authentication or configuration issue");
                    }
                }
            }
            _ = chatlog_task => {
                info!("Chatlog task exited");
            }
            _ = channel_refresh_task => {
                info!("Channel refresh task exited");
            }
        }

        // Flush any remaining chat messages
        info!("Flushing pending chat messages...");
        chatlog_service.flush().await?;

        info!("Bot shut down gracefully");
        Ok(())
    }
}
