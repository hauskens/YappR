use twitch_api::{
    client::ClientDefault, types::UserId, HelixClient
};
use twitch_oauth2::UserToken;
use yappr::bots::websocket;
use yappr::bots::twitch_auth;
use eyre::WrapErr;

#[tokio::main]
async fn main() -> Result<(), eyre::Report> {
    // Set up logging
    tracing_subscriber::fmt::fmt()
        .with_writer(std::io::stderr)
        .init();
        
    println!("Starting Twitch bot...");

    let token = if let Ok(token) = twitch_auth::get_user_token().await {
        token
    } else {
        eyre::bail!("Failed to get user token");
    };

    let client: HelixClient<'static, reqwest::Client> = twitch_api::HelixClient::with_client(
        ClientDefault::default_client_with_name(Some("yappr_bot".parse()?))?);
    let bot = Bot {
        client,
        token,
        bot_user_id: UserId::from("1313494860"),
    };
    bot.start().await?;
    Ok(())
}

pub struct Bot {
    pub client: HelixClient<'static, reqwest::Client>,
    pub token: UserToken,
    pub bot_user_id: UserId,
}

impl Bot {
    pub async fn start(&self) -> Result<(), eyre::Report> {
        let websocket_client = websocket::WebsocketClient {
            session_id: None,
            token: self.token.clone(),
            client: self.client.clone(),
            connect_url: twitch_api::TWITCH_EVENTSUB_WEBSOCKET_URL.clone(),
            chats: vec![UserId::from("25620302")],
            bot_user_id: self.bot_user_id.clone(),
        };
        let websocket_client = tokio::spawn(async move { websocket_client.run().await });

        tokio::try_join!(flatten(websocket_client))?;
        Ok(())
    }
}
    
async fn flatten<T>(
    handle: tokio::task::JoinHandle<Result<T, eyre::Report>>,
) -> Result<T, eyre::Report> {
    match handle.await {
        Ok(Ok(result)) => Ok(result),
        Ok(Err(err)) => Err(err),
        Err(e) => Err(e).wrap_err_with(|| "handling failed"),
    }
}