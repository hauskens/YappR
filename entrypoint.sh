#!/usr/bin/env sh
set +e
echo "------------"
echo "Running DB migrations"
echo "------------"
alembic upgrade head
echo "------------"
echo "Starting application"
echo "------------"
gunicorn --config gunicorn_config.py 'app.main:app'
