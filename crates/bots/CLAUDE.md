# yappr-bot (Bot Services)

**Purpose**: Twitch and Discord bots for community interaction, clip submissions, and chat logging.

**Structure**:
```
src/
  lib.rs              # Core module re-exports
  twitch_bot.rs       # Twitch bot entry point
  discord_bot.rs      # Discord bot entry point
  core/
    - message.rs      # Message type definitions
    - moderation.rs   # Core moderation logic
  services/
    - chatlog_service.rs (Chat logging)
    - user_service.rs (User tracking)
  twitch/             # Twitch-specific implementation
    - auth.rs (OAuth token management)
    - message_handler.rs (Message processing)
    - moderation_handler.rs (Moderation)
    - websocket.rs (EventSub WebSocket)
    - channel_manager.rs (Channel subscriptions)
    - message.rs, moderation.rs
  discord/            # Discord-specific implementation
    - message_handler.rs (Message commands)
    - reactions.rs (Reaction handling)
    - commands.rs (Slash commands)
    - moderation.rs (Discord moderation)
```

**Twitch Bot Features**:
- Uses Twitch EventSub WebSocket API for real-time events
- Listens to chat messages and clip submissions
- Moderator-based permissions
- Integrates with content queue
- Logs chat messages to database

**Discord Bot Features**:
- Slash commands for clip submission
- Reaction-based voting system
- Message command processing
- Moderator permissions

**Architecture Notes**:
- Uses Serenity for Discord bot framework
- Uses Twitch API client with EventSub
- Arc-wrapped services for thread-safe sharing
- Database queries for user/channel lookups