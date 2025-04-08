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
	flask --app app.main --debug run --host=0.0.0.0
else
	gunicorn --config gunicorn_config.py 'app.main:app'
fi
