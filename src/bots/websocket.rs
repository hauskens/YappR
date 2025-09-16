use eyre::Context;
use tokio_tungstenite::tungstenite;
use twitch_api::{
    eventsub::{
        self,
        event::websocket::{EventsubWebsocketData, ReconnectPayload, SessionData, WelcomePayload},
        Event,
    },
    types::{self},
    HelixClient,
};
use twitch_oauth2::{TwitchToken, UserToken};
use crate::bots::twitch_auth;

pub struct WebsocketClient {
    /// The session id of the websocket connection
    pub session_id: Option<String>,
    /// The token used to authenticate with the Twitch API
    pub token: UserToken,
    /// The client used to make requests to the Twitch API
    pub client: HelixClient<'static, reqwest::Client>,
    /// The url to use for websocket
    pub connect_url: url::Url,
    pub chats: Vec<types::UserId>,
    pub bot_user_id: types::UserId,
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
        let config = tungstenite::protocol::WebSocketConfig {
            max_message_size: Some(64 << 20), // 64 MiB
            max_frame_size: Some(16 << 20),   // 16 MiB
            accept_unmasked_frames: false,
            ..tungstenite::protocol::WebSocketConfig::default()
        };
        let (socket, _) =
            tokio_tungstenite::connect_async_with_config(&self.connect_url, Some(config), false)
                .await
                .context("Can't connect")?;

        Ok(socket)
    }

    /// Run the websocket subscriber
    #[tracing::instrument(name = "subscriber", skip_all, fields())]
    pub async fn run(mut self) -> Result<(), eyre::Error> {
        // Establish the stream
        let mut s = self
            .connect()
            .await
            .context("when establishing connection")?;
        // Loop over the stream, processing messages as they come in.
        loop {
            tokio::select!(
            Some(msg) = futures::StreamExt::next(&mut s) => {
                let msg = match msg {
                    Err(tungstenite::Error::Protocol(
                        tungstenite::error::ProtocolError::ResetWithoutClosingHandshake,
                    )) => {
                        tracing::warn!(
                            "connection was sent an unexpected frame or was reset, reestablishing it"
                        );
                        s = self
                            .connect()
                            .await
                            .context("when reestablishing connection")?;
                        continue
                    }
                    _ => msg.context("when getting message")?,
                };
                self.process_message(msg).await?
            })
        }
    }

    /// Process a message from the websocket
    pub async fn process_message(&mut self, msg: tungstenite::Message) -> Result<(), eyre::Report> {
        match msg {
            tungstenite::Message::Text(s) => {
                tracing::info!("{s}");
                // Parse the message into a [twitch_api::eventsub::EventsubWebsocketData]
                match Event::parse_websocket(&s)? {
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
                    } => eyre::bail!("got revocation event: {metadata:?}"),
                    EventsubWebsocketData::Notification {
                        metadata: _,
                        payload,
                    } => {
                        match payload {
                            Event::ChannelChatMessageV1(eventsub::Payload { message, .. }) => {
                                tracing::info!(?message, "got chat message");
                            }
                            Event::ChannelChatClearUserMessagesV1(eventsub::Payload { message, .. }) => {
                                tracing::info!(?message, "got chat message delete");
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
                }
            }
            tungstenite::Message::Close(_) => todo!(),
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
            self.token =
                twitch_auth::get_user_token().await?;
        }
        let transport = eventsub::Transport::websocket(data.id.clone());
        let subscription = eventsub::channel::ChannelChatMessageV1::new(self.chats[0].clone(), self.bot_user_id.clone());
        let message_delete_subscription = eventsub::channel::ChannelChatClearUserMessagesV1::new(self.chats[0].clone(), self.bot_user_id.clone());
        tracing::info!("Creating subscription for broadcaster_user_id: {:?}, user_id: {:?}", self.chats[0], self.bot_user_id);
        tracing::info!("Token scopes: {:?}", self.token.scopes());
        
        match self.client
            .create_eventsub_subscription(
                subscription,
                transport.clone(),
                &self.token,
            )
            .await {
                Ok(sub) => {
                    tracing::info!("Successfully created subscription: {:?}", sub);
                },
                Err(e) => {
                    tracing::error!("Failed to create subscription: {:?}", e);
                    return Err(e.into());
                }
            }
        match self.client
            .create_eventsub_subscription(
                message_delete_subscription,
                transport.clone(),
                &self.token,
            )
            .await {
                Ok(sub) => {
                    tracing::info!("Successfully created subscription: {:?}", sub);
                },
                Err(e) => {
                    tracing::error!("Failed to create subscription: {:?}", e);
                    return Err(e.into());
                }
            }
        Ok(())
    }
}