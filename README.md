# YappR - Metadata and Transcription Search

=====================================

A self-hosted, open-source project for searching through transcriptions on
YouTube channels.

## Overview

YappR is a metadata and transcription search tool that allows you to store and
query metadata from various YouTube channels. The project provides a flexible
and extensible framework for storing/processing transcription data.

## Attribution

This project was originally inspired by and would not have happened without the
project [SqueexVodSearch](https://github.com/lawrencehook/SqueexVodSearch) by
[@lawrencehook](https://github.com/lawrencehook).

## Running the project

To run the project with Docker, simply clone this project and run:

```bash
docker compose up --build
```

You should change the configuration to avoid a insecure setup!

## Configuration

All environment variables comes from `app/models/config.py`

| **Environment Variable** | **Default Value**                                                          | **Description**                                   |
| ------------------------ | -------------------------------------------------------------------------- | ------------------------------------------------- |
| `APP_SECRET`             | `somethingrandom`                                                          | Application secret key                            |
| `DB_URI`                 | `postgresql+psycopg://postgres:mysecretpassword@postgres-db:5432/postgres` | Database URI (PostgreSQL)                         |
| `LOG_LEVEL`              | `logging.DEBUG`                                                            | Log level (debug, info, warning, error, critical) |
| `STORAGE_LOCATION`       | `/var/lib/yappr/data`                                                      | Storage location for files or data                |
| `CACHE_LOCATION`         | `/var/lib/yappr/cache`                                                     | Cache location for cached data                    |
| `REDIS_URI`              | `redis://redis-cache:6379/0`                                               | Redis URI (connection string)                     |
| `PORT`                   | `5000`                                                                     | Application port number                           |
| `HOST`                   | `0.0.0.0`                                                                  | Application host IP address                       |

## Development dependencies

You can get a development environment running with either:

```bash
docker compose up --build --watch
```

```bash
nix develop
uv run app/main.py
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
