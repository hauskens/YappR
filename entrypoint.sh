#!/usr/bin/env sh
echo "------------"
echo "Running DB migrations"
echo "------------"
alembic upgrade head
echo "------------"
echo "Starting application"
echo "------------"
python3 app/main.py
