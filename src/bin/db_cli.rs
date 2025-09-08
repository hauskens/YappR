use clap::{Parser, Subcommand};
use sea_orm::*;
use yappr::database;
use yappr::entities::prelude::*;
use yappr::services::broadcaster::BroadcasterService;
use yappr::services::user::UserService;

#[derive(Parser)]
#[command(name = "DB CLI")]
#[command(about = "Just a util to list out database records")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// List all users
    Users,
    /// List all broadcasters
    Broadcasters,
    /// List all channels
    Channels,
    /// List bot user
    BotUser,
    /// Count records in a table
    Count { table: String },
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    let db = database::get_database_connection().await?;

    match cli.command {
        Commands::Users => {
            let users = Users::find().limit(10).all(&db).await?;
            println!("Found {} users:", users.len());
            for user in users {
                println!("  ID: {}, Account Type: {:?}", user.id, user.account_type);
            }
        }
        Commands::Broadcasters => {
            let broadcaster_service = BroadcasterService::new(db);
            let broadcasters = broadcaster_service.get_all(None).await?;
            println!("Found {} broadcasters:", broadcasters.len());
            for broadcaster in broadcasters {
                println!(
                    "  ID: {}, Name: {}",
                    broadcaster.id, broadcaster.name
                );
            }
        }
        Commands::BotUser => {
            let user_service = UserService::new(db);
            let bot_user = user_service.get_bot_user().await?;
            let bot_oauth = user_service.get_user_oauth_token(bot_user.id).await?;
            println!("Bot user: {} , Oauth access token: {} , Oauth refresh token: {}", bot_user.name, bot_oauth.as_ref().unwrap().access_token, bot_oauth.as_ref().unwrap().refresh_token);
        }
        Commands::Channels => {
            let channels = Channels::find().limit(10).all(&db).await?;
            println!("Found {} channels:", channels.len());
            for channel in channels {
                println!(
                    "  ID: {}, Platform Ref: {}, Platform Name: {}",
                    channel.id, channel.platform_ref, channel.platform_name
                );
            }
        }
        Commands::Count { table } => {
            let count = match table.as_str() {
                "users" => Users::find().count(&db).await?,
                "broadcasters" => Broadcaster::find().count(&db).await?,
                "channels" => Channels::find().count(&db).await?,
                "segments" => Segments::find().count(&db).await?,
                "transcriptions" => Transcriptions::find().count(&db).await?,
                "chatlogs" => Chatlogs::find().count(&db).await?,
                _ => {
                    println!("Unknown table: {}", table);
                    println!(
                        "Available tables: users, broadcasters, channels, segments, transcriptions, chatlogs"
                    );
                    return Ok(());
                }
            };
            println!("Table '{}' has {} records", table, count);
        }
    }

    Ok(())
}
