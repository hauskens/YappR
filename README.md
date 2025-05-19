# YappR - Metadata and Transcription Search

=====================================

A self-hosted, open-source project for searching and transcribing audio from YouTube and Twitch.

## Overview

YappR is a metadata and transcription search tool that allows you to store and
query metadata from various YouTube channels. The project provides a flexible
and extensible framework for storing/processing transcription data.

Some of the features include:

- A web interface to search and manage transcriptions across twitch and youtube for any channel
- Task scheduler to extract and process audio
- GPU worker to transcribe audio, multiple workers can be connected
- Authenticated web interface using Discord OAuth2, guests are rate limited


## Technologies used
- Python
- FastAPI
- Twitch and YouTube API
- PostgreSQL
- Alembic (db migrations)
- Redis
- Celery (task scheduler)
- pgvector (search)
- WhisperX (transcription)
- Yt-dlp (audio download)


## Attribution

This project was originally inspired by and would not have happened without the
project [SqueexVodSearch](https://github.com/lawrencehook/SqueexVodSearch) by
[@lawrencehook](https://github.com/lawrencehook).

Also thanks to [NLQotes](https://github.com/irinelul/NLQuotes) for inspiration
to use `tsvector` in PostgreSQL

## Running the project

Nvidia GPU is required to run the transcription workers.
To run the project with Docker, simply clone this project, and create a `.env` file based on the [configuration](#configuration) values.
Edit the docker-compose.yml file to set how many workers you want to run, gpu workers are disabled by default and should only be 1 per gpu.

```bash
docker compose up --build
```

You should change the configuration to avoid a insecure setup!

## Configuration

All environment variables comes from `app/models/config.py`

| **Environment Variable** | **Default Value**                                                          | **Description**                                   |
| ------------------------ | -------------------------------------------------------------------------- | ------------------------------------------------- |
| `APP_SECRET`             | `ajsdlfknsdkfjnsdafiouswe`                                                 | Application secret key                            |
| `APP_URL`                | `http://127.0.0.1:5000`                                                    | Application URL                                   |
| `DB_URI`                 | `postgresql+psycopg://postgres:mysecretpassword@postgres-db:5432/postgres` | Database URI (PostgreSQL)                         |
| `LOG_LEVEL`              | `logging.DEBUG`                                                            | Log level (debug, info, warning, error, critical) |
| `DEBUG`                  | `False`                                                                    | Enable debug mode                                 |
| `STORAGE_LOCATION`       | `/var/lib/yappr/data`                                                      | Storage location for files or data                |
| `CACHE_LOCATION`         | `/var/lib/yappr/cache`                                                     | Cache location for cached data                    |
| `REDIS_URI`              | `redis://redis-cache:6379/0`                                               | Redis URI (connection string)                     |
| `PORT`                   | `5000`                                                                     | Application listen port                           |
| `HOST`                   | `0.0.0.0`                                                                  | Application listen IP address                       |
| `NLTK_DATA`              | `/var/lib/yappr/nltk`                                                      | Path for NLTK data                                |
| `DISCORD_CLIENT_ID`      | `None`                                                                     | Discord client ID for OAuth2                      |
| `DISCORD_CLIENT_SECRET`  | `None`                                                                     | Discord client secret for OAuth2                  |
| `DISCORD_REDIRECT_URI`   | `None`                                                                     | Discord OAuth2 redirect URI                       |
| `YOUTUBE_API_KEY`        | `None`                                                                     | YouTube Data API key                              |
| `WEBSHARE_PROXY_USERNAME`| `None`                                                                     | Webshare proxy username - _optional_              |
| `WEBSHARE_PROXY_PASSWORD`| `None`                                                                     | Webshare proxy password - _optional_              |
| `TWITCH_CLIENT_ID`       | `None`                                                                     | Twitch API client ID - |
| `TWITCH_CLIENT_SECRET`   | `None`                                                                     | Twitch API client secret |
| `TWITCH_DL_GQL_CLIENT_ID`| `None`                                                                     | Twitch GraphQL client ID _optional_ used when downloading audio, if behind subscription |
| `TRANSCRIPTION_DEVICE`   | `cuda`                                                                      | Device for transcription (cpu/cuda)                |
| `TRANSCRIPTION_MODEL`    | `large-v2`                                                                 | Whisper model size                                |
| `TRANSCRIPTION_COMPUTE_TYPE`| `float16`                                    | Compute type for transcription (float16/int8)     |
| `TRANSCRIPTION_BATCH_SIZE`| `8`                                          | Batch size for transcription                     |
| `API_KEY`                | `not_a_secure_key!11`                                                      | Application API key, used by remote workers to authenticate, needs to match on remote workers                               |
| `HF_TOKEN`               | `None`                                                                     | Hugging Face API token _optional_                            |

## API Key Information

### YouTube API Key
- Go to [Google Cloud Console](https://console.cloud.google.com/)
- Create a new project or select an existing one
- Enable the YouTube Data API v3
- Create credentials -> API key
- Restrict the API key to YouTube Data API v3 if desired
- Copy the API key and set it as `YOUTUBE_API_KEY`

### Twitch API Keys
- Go to [Twitch Developer Console](https://dev.twitch.tv/console/apps)
- Create a new application
- Set the OAuth redirect URI (if needed)
- Copy the Client ID and Client Secret
- Set them as `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`

### Discord API Keys
- Go to [Discord Developer Portal](https://discord.com/developers/applications)
- Create a new application
- Copy the Client ID and Client Secret
- Set them as `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET`
- Set the OAuth2 redirect URI as `DISCORD_REDIRECT_URI`

### Hugging Face Token
- Go to [Hugging Face](https://huggingface.co/)
- Create an account if needed
- Go to your settings -> Access Tokens
- Generate a new token
- Set it as `HF_TOKEN`

## Development dependencies

You can get a development environment running with either:

```bash
docker compose up --build --watch
```

Or if you have [UV](https://github.com/astral-sh/uv) and python installed, you
can run

```bash
uv run app/main.py
```

## Database migrations

Database migrations are handled by Alembic in the `app/db` folder. While running
in docker it will automatically run the migrations at startup.

### Creating revisions

- Check that your `alembic.ini` file is configured towards your local db.
- `uv run alembic revision --autogenerate -m 'my commit message here'`
- `uv run alembic upgrade head`

if you regret, run `uv run alembic downgrade -1`

## Contributing

Contributions are welcome! If you'd like to contribute, please fork the
repository, make changes as needed, and submit a pull request.

## License

YappR is released under the **GNU General Public License (GPL) version 2**.
