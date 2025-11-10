use sea_orm::{ActiveModelTrait, ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter, Set};
use serenity::all::{
    CommandInteraction, Context, CreateCommand, CreateInteractionResponse,
    CreateInteractionResponseMessage,
};
use std::collections::HashSet;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{error, info};
use yappr_shared::entities::{broadcaster_settings, prelude::*};

/// Handler for Discord slash commands
pub struct CommandHandler {
    db: DatabaseConnection,
    /// Set of channel IDs that are actively being listened to
    active_listening_channels: Arc<RwLock<HashSet<u64>>>,
}

impl CommandHandler {
    pub fn new(
        db: DatabaseConnection,
        active_listening_channels: Arc<RwLock<HashSet<u64>>>,
    ) -> Self {
        Self {
            db,
            active_listening_channels,
        }
    }

    /// Register all slash commands
    pub fn register_commands() -> Vec<CreateCommand> {
        vec![
            CreateCommand::new("verify").description("Verify a channel for the bot to listen to"),
            CreateCommand::new("test").description("Test command for debugging"),
        ]
    }

    /// Handle a command interaction
    pub async fn handle_command(
        &self,
        ctx: &Context,
        interaction: &CommandInteraction,
    ) -> Result<(), eyre::Report> {
        match interaction.data.name.as_str() {
            "verify" => self.handle_verify(ctx, interaction).await,
            "test" => self.handle_test(ctx, interaction).await,
            _ => {
                error!("Unknown command: {}", interaction.data.name);
                Ok(())
            }
        }
    }

    /// Handle /verify command
    async fn handle_verify(
        &self,
        ctx: &Context,
        interaction: &CommandInteraction,
    ) -> Result<(), eyre::Report> {
        // Defer response (ephemeral)
        interaction
            .create_response(
                &ctx.http,
                CreateInteractionResponse::Defer(
                    CreateInteractionResponseMessage::new().ephemeral(true),
                ),
            )
            .await?;

        let channel_id = interaction.channel_id.get();

        info!(channel_id = channel_id, "Processing /verify command");

        // Find broadcaster settings with this channel ID
        let broadcaster_setting = BroadcasterSettings::find()
            .filter(broadcaster_settings::Column::LinkedDiscordChannelId.eq(channel_id as i64))
            .one(&self.db)
            .await?;

        if let Some(setting) = broadcaster_setting {
            // Check if already verified and in active listening channels
            let is_active = {
                let channels = self.active_listening_channels.read().await;
                channels.contains(&channel_id)
            };

            if setting.linked_discord_channel_verified && is_active {
                // Already verified
                interaction
                    .edit_response(
                        &ctx.http,
                        serenity::all::EditInteractionResponse::new()
                            .content("✅ This channel is already verified"),
                    )
                    .await?;

                info!(
                    channel_id = channel_id,
                    broadcaster_id = setting.broadcaster_id,
                    "Channel already verified"
                );
            } else {
                // Verify the channel
                let mut active: broadcaster_settings::ActiveModel = setting.into();
                active.linked_discord_channel_verified = Set(true);
                active.update(&self.db).await?;

                // Add to active listening channels
                {
                    let mut channels = self.active_listening_channels.write().await;
                    channels.insert(channel_id);
                }

                interaction
                    .edit_response(
                        &ctx.http,
                        serenity::all::EditInteractionResponse::new()
                            .content(format!(
                                "✅ Channel verified and now listening to messages in <#{}>, clips posted here will be added to the content queue.",
                                channel_id
                            )),
                    )
                    .await?;

                info!(channel_id = channel_id, "Channel verified successfully");
            }
        } else {
            // Not linked
            interaction
                .edit_response(
                    &ctx.http,
                    serenity::all::EditInteractionResponse::new()
                        .content(format!(
                            "❌ This discord channel is not linked to a broadcaster. In YappR, go to a Broadcaster > Broadcast Settings > Linked Discord Channel and add the channel id: `{}`.",
                            channel_id
                        )),
                )
                .await?;

            info!(channel_id = channel_id, "Channel not linked to broadcaster");
        }

        Ok(())
    }

    /// Handle /test command
    async fn handle_test(
        &self,
        ctx: &Context,
        interaction: &CommandInteraction,
    ) -> Result<(), eyre::Report> {
        // Defer response (ephemeral)
        interaction
            .create_response(
                &ctx.http,
                CreateInteractionResponse::Defer(
                    CreateInteractionResponseMessage::new().ephemeral(true),
                ),
            )
            .await?;

        info!("Processing /test command");

        interaction
            .edit_response(
                &ctx.http,
                serenity::all::EditInteractionResponse::new().content("Test command"),
            )
            .await?;

        Ok(())
    }

    /// Load verified channels from database on startup
    pub async fn load_verified_channels(&self) -> Result<(), eyre::Report> {
        let settings = BroadcasterSettings::find()
            .filter(broadcaster_settings::Column::LinkedDiscordChannelId.is_not_null())
            .filter(broadcaster_settings::Column::LinkedDiscordChannelVerified.eq(true))
            .all(&self.db)
            .await?;

        let mut channels = self.active_listening_channels.write().await;
        for setting in settings {
            if let Some(channel_id_i64) = setting.linked_discord_channel_id {
                let channel_id = channel_id_i64 as u64;
                channels.insert(channel_id);
                info!(
                    channel_id = channel_id,
                    broadcaster_id = setting.broadcaster_id,
                    "Loaded verified channel"
                );
            }
        }

        info!(count = channels.len(), "Loaded verified Discord channels");

        Ok(())
    }

    /// Get broadcaster_id for a channel (if verified)
    pub async fn get_broadcaster_for_channel(
        &self,
        channel_id: u64,
    ) -> Result<Option<i32>, eyre::Report> {
        let setting = BroadcasterSettings::find()
            .filter(broadcaster_settings::Column::LinkedDiscordChannelId.eq(channel_id as i64))
            .filter(broadcaster_settings::Column::LinkedDiscordChannelVerified.eq(true))
            .one(&self.db)
            .await?;

        Ok(setting.map(|s| s.broadcaster_id))
    }
}
