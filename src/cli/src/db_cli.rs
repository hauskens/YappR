use clap::Parser;
use sea_orm::*;
use yappr_shared::entities::prelude::*;
use yappr_shared::services::broadcaster::BroadcasterService;
use yappr_shared::services::user::UserService;
use yappr_shared::chatlog_parser;
use yappr_shared::database;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(name = "DB CLI", version, about = "Just a util to list out database records")]
struct Args {
    /// Action to perform
    #[arg(short, long, value_name = "ACTION", default_value = "list", 
          help = "Action to perform: users, broadcasters, channels, bot-user, count, parse-chatlogs")]
    action: String,

    // Count command options
    /// Table name for count action
    #[arg(long, value_name = "TABLE", help = "Table to count records for (users, broadcasters, channels, segments, transcriptions, chatlogs)")]
    table: Option<String>,

    // Parse chatlogs command options
    /// Path to a log file or directory containing log files
    #[arg(long, value_name = "PATH", help = "Path to log file or directory for parse-chatlogs action")]
    path: Option<PathBuf>,
    
    /// Channel ID to associate messages with
    #[arg(long, value_name = "ID", help = "Channel ID for parse-chatlogs action")]
    channel_id: Option<i32>,
    
    /// User ID who is importing (for creating import record)
    #[arg(long, value_name = "ID", help = "User ID performing import for parse-chatlogs action")]
    imported_by: Option<i32>,
    
    /// Override timezone string (e.g., "US/Eastern", "UTC")
    #[arg(long, value_name = "TZ", help = "Override timezone for parse-chatlogs action")]
    timezone: Option<String>,
    
    /// Import only events, skip chat messages
    #[arg(long, help = "Import only events for parse-chatlogs action")]
    events_only: bool,
    
    /// Timestamp margin in milliseconds for duplicate detection
    #[arg(long, value_name = "MS", default_value = "1000", help = "Timestamp margin for parse-chatlogs action")]
    margin_ms: i64,
    
    /// Perform a dry run without inserting data into the database
    #[arg(long, help = "Dry run mode for parse-chatlogs action")]
    dry_run: bool,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();
    let db = database::get_database_connection().await?;

    match args.action.as_str() {
        "users" => {
            let users = Users::find().limit(10).all(&db).await?;
            println!("Found {} users:", users.len());
            for user in users {
                println!("  ID: {}, Account Type: {:?}", user.id, user.account_type);
            }
        }
        "broadcasters" => {
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
        "bot-user" => {
            let user_service = UserService::new(db);
            let bot_user = user_service.get_bot_user().await?;
            let bot_oauth = user_service.get_user_oauth_token(bot_user.id).await?;
            println!("Bot user: {} , Oauth access token: {} , Oauth refresh token: {}", bot_user.name, bot_oauth.as_ref().unwrap().access_token, bot_oauth.as_ref().unwrap().refresh_token);
        }
        "channels" => {
            let channels = Channels::find().limit(10).all(&db).await?;
            println!("Found {} channels:", channels.len());
            for channel in channels {
                println!(
                    "  ID: {}, Platform Ref: {}, Platform Name: {}",
                    channel.id, channel.platform_ref, channel.platform_name
                );
            }
        }
        "count" => {
            let table = args.table.ok_or("--table is required for count action")?;
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
        "parse-chatlogs" => {
            let path = args.path.ok_or("--path is required for parse-chatlogs action")?;
            let channel_id = args.channel_id.ok_or("--channel-id is required for parse-chatlogs action")?;
            
            chatlog_parser::parse_chatlogs_command(
                &db,
                path,
                channel_id,
                args.imported_by.unwrap(),
                args.timezone,
                args.events_only,
                args.margin_ms,
                args.dry_run,
            )
            .await?;
        }
        _ => {
            println!("Unknown action: {}", args.action);
            println!("Available actions: users, broadcasters, channels, bot-user, count, parse-chatlogs");
            return Ok(());
        }
    }

    Ok(())
}
