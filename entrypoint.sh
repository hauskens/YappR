#!/usr/bin/env sh
set +e
echo "------------"
echo "Running DB migrations"
echo "------------"
alembic upgrade head

if [ "$DEBUG" = true ]; then
	echo "------------"
	echo "Starting TypeScript watcher in background"
	echo "------------"
	mkdir -p app/static/js
	bun run watch:ts &
	TS_PID=$!
	echo "TypeScript watcher started (PID: $TS_PID)"
fi

echo "------------"
echo "Starting application"
echo "------------"
if [ "$DEBUG" = true ]; then
	python -m app.main
else
	gunicorn --config gunicorn_config.py 'app.main:app'
fi
