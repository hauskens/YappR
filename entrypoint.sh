#!/usr/bin/env sh
set +e
echo "------------"
echo "Running DB migrations"
echo "------------"
alembic upgrade head
echo "------------"
echo "Starting application"
echo "------------"
if [ "$DEBUG" = true ]; then
	python -m app.main
else
	gunicorn --config gunicorn_config.py 'app.main:app'
fi
