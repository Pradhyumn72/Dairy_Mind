#!/bin/bash

# Wait for MySQL to be ready
echo "Waiting for MySQL..."
while ! nc -z db 3306; do
  sleep 0.1
done
echo "MySQL started."

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Start Gunicorn server
echo "Starting Gunicorn..."
exec gunicorn dairymind.wsgi:application --bind 0.0.0.0:8000
