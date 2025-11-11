use crate::twitch::{
    auth, channel_manager::ChannelManager, message_handler::MessageHandler,
    moderation_handler::ModerationHandler,
};
use eyre::Context;
use std::sync::Arc;
use std::time::Duration;
use tokio_tungstenite::tungstenite;
use twitch_api::{
    HelixClient,
    eventsub::{
        self, Event,
        event::websocket::{EventsubWebsocketData, ReconnectPayload, SessionData, WelcomePayload},
    },
    types::{self},
};
use twitch_oauth2::{TwitchToken, UserToken};

pub struct WebsocketClient {
    /// The session id of the websocket connection
    pub session_id: Option<String>,
    /// The token used to authenticate with the Twitch API
    pub token: UserToken,
    /// The client used to make requests to the Twitch API
    pub client: HelixClient<'static, reqwest::Client>,
    /// The url to use for websocket
    pub connect_url: url::Url,
    /// Channels currently subscribed to
    pub subscribed_channels: Vec<String>,
    pub bot_user_id: types::UserId,
    /// Channel manager for settings and subscription management
    pub channel_manager: Arc<ChannelManager>,
    /// Message handler for processing chat messages
    pub message_handler: Arc<MessageHandler>,
    /// Moderation handler for processing moderation events
    pub moderation_handler: Arc<ModerationHandler>,
    /// Number of consecutive connection failures
    pub consecutive_failures: u32,
    /// Current backoff duration for reconnection attempts
    pub current_backoff: Duration,
}

impl WebsocketClient {
    /// Connect to the websocket and return the stream
    pub async fn connect(
        &self,
    ) -> Result<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        eyre::Error,
    > {
        tracing::info!("connecting to twitch");
        let mut config = tungstenite::protocol::WebSocketConfig::default();
        config.max_message_size = Some(64 << 20); // 64 MiB
        config.max_frame_size = Some(16 << 20); // 16 MiB
        config.accept_unmasked_frames = false;
        let (socket, _) =
            tokio_tungstenite::connect_async_with_config(&self.connect_url, Some(config), false)
                .await
                .context("Can't connect")?;

        Ok(socket)
    }

    /// Reset connection state after successful connection
    fn reset_backoff(&mut self) {
        self.consecutive_failures = 0;
        self.current_backoff = Duration::from_secs(1);
    }

    /// Increase backoff after a connection failure
    fn increase_backoff(&mut self) {
        self.consecutive_failures += 1;
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, 64s, capped at 5 minutes
        let max_backoff = Duration::from_secs(300); // 5 minutes
        self.current_backoff = std::cmp::min(
            Duration::from_secs(1u64 << std::cmp::min(self.consecutive_failures, 8)),
            max_backoff,
        );
    }

    /// Check if an error is recoverable and should trigger reconnection
    fn is_recoverable_error(error: &tungstenite::Error) -> bool {
        matches!(
            error,
            tungstenite::Error::ConnectionClosed
                | tungstenite::Error::AlreadyClosed
                | tungstenite::Error::Io(_)
                | tungstenite::Error::Protocol(
                    tungstenite::error::ProtocolError::ResetWithoutClosingHandshake
                )
        )
    }

    /// Run the websocket subscriber
    #[tracing::instrument(name = "subscriber", skip_all, fields())]
    pub async fn run(mut self) -> Result<(), eyre::Error> {
        // Establish the stream
        let mut s = self
            .connect()
            .await
            .context("when establishing initial connection")?;

        // Reset backoff on successful initial connection
        self.reset_backoff();

        // Loop over the stream, processing messages as they come in.
        loop {
            tokio::select!(
            Some(msg) = futures::StreamExt::next(&mut s) => {
                match msg {
                    Ok(message) => {
                        // Successfully received a message, reset backoff
                        self.reset_backoff();

                        // Process the message
                        if let Err(e) = self.process_message(message).await {
                            tracing::error!(error = %e, "Failed to process message");
                            // Continue running even if message processing fails
                        }
                    }
                    Err(e) if Self::is_recoverable_error(&e) => {
                        // Recoverable error, attempt reconnection with backoff
                        self.increase_backoff();

                        tracing::warn!(
                            error = %e,
                            consecutive_failures = self.consecutive_failures,
                            backoff_secs = self.current_backoff.as_secs(),
                            "WebSocket error, reconnecting after backoff"
                        );

                        // Wait for backoff duration
                        tokio::time::sleep(self.current_backoff).await;

                        // Attempt to reconnect
                        match self.connect().await {
                            Ok(new_stream) => {
                                s = new_stream;
                                tracing::warn!("Successfully reconnected to WebSocket");
                                continue;
                            }
                            Err(connect_error) => {
                                tracing::warn!(
                                    error = %connect_error,
                                    "Failed to reconnect, will retry"
                                );
                                // Continue loop to try again
                                continue;
                            }
                        }
                    }
                    Err(e) => {
                        // Unrecoverable error, propagate up
                        return Err(e).context("Unrecoverable WebSocket error");
                    }
                }
            },
            else => {
                tracing::info!("stream ended, exiting websocket loop");
                break;
            })
        }
        Ok(())
    }

    /// Process a message from the websocket
    pub async fn process_message(&mut self, msg: tungstenite::Message) -> Result<(), eyre::Report> {
        match msg {
            tungstenite::Message::Text(s) => match Event::parse_websocket(&s)? {
                EventsubWebsocketData::Welcome {
                    payload: WelcomePayload { session },
                    ..
                }
                | EventsubWebsocketData::Reconnect {
                    payload: ReconnectPayload { session },
                    ..
                } => {
                    self.process_welcome_message(session).await?;
                    Ok(())
                }
                EventsubWebsocketData::Revocation {
                    metadata,
                    payload: _,
                } => {
                    tracing::warn!("got revocation event: {metadata:?}");
                    Ok(())
                }
                EventsubWebsocketData::Notification {
                    metadata: _,
                    payload,
                } => {
                    match payload {
                        Event::ChannelChatMessageV1(ev_payload) => {
                            if let twitch_api::eventsub::Message::Notification(notif) =
                                &ev_payload.message
                            {
                                self.handle_chat_message(notif).await?;
                            }
                        }
                        Event::ChannelChatClearUserMessagesV1(ev_payload) => {
                            if let twitch_api::eventsub::Message::Notification(notif) =
                                &ev_payload.message
                            {
                                self.handle_moderation_event(notif).await?;
                            }
                        }
                        _ => {}
                    }
                    Ok(())
                }
                EventsubWebsocketData::Keepalive {
                    metadata: _,
                    payload: _,
                } => Ok(()),
                _ => Ok(()),
            },
            tungstenite::Message::Close(_) => {
                tracing::info!("connection closed");
                Ok(())
            }
            _ => Ok(()),
        }
    }

    pub async fn process_welcome_message(
        &mut self,
        data: SessionData<'_>,
    ) -> Result<(), eyre::Report> {
        self.session_id = Some(data.id.to_string());
        if let Some(url) = data.reconnect_url {
            self.connect_url = url.parse()?;
        }
        // check if the token is expired, if it is, request a new token. This only works if using a oauth service for getting a token
        if self.token.is_elapsed() {
            self.token = auth::get_user_token().await?;
        }
        let transport = eventsub::Transport::websocket(data.id.clone());

        // Get enabled channels from channel manager
        let enabled_channels = self.channel_manager.get_enabled_channel_ids().await;

        if enabled_channels.is_empty() {
            tracing::warn!("No enabled channels found, skipping subscriptions");
            return Ok(());
        }

        tracing::info!(
            channel_count = enabled_channels.len(),
            "Creating subscriptions for enabled channels"
        );

        // Create subscriptions for each enabled channel
        for channel_id in &enabled_channels {
            let broadcaster_id = types::UserId::new(channel_id.clone());

            // Create chat message subscription
            let chat_subscription = eventsub::channel::ChannelChatMessageV1::new(
                broadcaster_id.clone(),
                self.bot_user_id.clone(),
            );

            match self
                .client
                .create_eventsub_subscription(chat_subscription, transport.clone(), &self.token)
                .await
            {
                Ok(_) => {
                    tracing::info!(broadcaster_id = %channel_id, "Created chat message subscription");
                }
                Err(e) => {
                    tracing::error!(broadcaster_id = %channel_id, error = %e, "Failed to create chat message subscription");
                }
            }

            // Create moderation event subscription
            let mod_subscription = eventsub::channel::ChannelChatClearUserMessagesV1::new(
                broadcaster_id.clone(),
                self.bot_user_id.clone(),
            );

            match self
                .client
                .create_eventsub_subscription(mod_subscription, transport.clone(), &self.token)
                .await
            {
                Ok(_) => {
                    tracing::info!(broadcaster_id = %channel_id, "Created moderation subscription");
                }
                Err(e) => {
                    tracing::error!(broadcaster_id = %channel_id, error = %e, "Failed to create moderation subscription");
                }
            }
        }

        self.subscribed_channels = enabled_channels;

        Ok(())
    }

    /// Handle incoming chat message
    async fn handle_chat_message(
        &self,
        payload: &twitch_api::eventsub::channel::chat::ChannelChatMessageV1Payload,
    ) -> Result<(), eyre::Report> {
        // Get channel settings
        let settings = match self
            .channel_manager
            .get_settings(payload.broadcaster_user_id.as_str())
            .await
        {
            Some(s) => s,
            None => {
                tracing::warn!(broadcaster_id = %payload.broadcaster_user_id, "No settings found for channel");
                return Ok(());
            }
        };

        // Process message
        self.message_handler
            .handle_message(payload, &settings)
            .await
    }

    /// Handle moderation event (timeout/ban)
    async fn handle_moderation_event(
        &self,
        payload: &twitch_api::eventsub::channel::chat::ChannelChatClearUserMessagesV1Payload,
    ) -> Result<(), eyre::Report> {
        // Get channel settings
        let settings = match self
            .channel_manager
            .get_settings(payload.broadcaster_user_id.as_str())
            .await
        {
            Some(s) => s,
            None => {
                tracing::warn!(broadcaster_id = %payload.broadcaster_user_id, "No settings found for channel");
                return Ok(());
            }
        };

        // Process moderation event
        self.moderation_handler
            .handle_moderation_event(payload, settings.channel_id, settings.broadcaster_id)
            .await
    }
}
