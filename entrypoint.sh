#!/bin/sh
set -e

# Start the scheduler in the background
echo "Starting scheduler..."
python -m src.scheduler &

# Start the web server in the foreground
echo "Starting web server on port 8000..."
exec uvicorn src.web.app:app --host 0.0.0.0 --port 8000
