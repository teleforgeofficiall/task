#!/usr/bin/env bash
set -euo pipefail

echo "[TASKHUB] Starting production server..."

# Run database migrations
echo "[TASKHUB] Running Alembic migrations..."
alembic upgrade head

# Clean up old backups in the background
echo "[TASKHUB] Starting periodic backup cleanup..."
(
    while true; do
        sleep 86400  # Run once per day
        python -c "from bot.backup.manager import BackupManager; import asyncio; asyncio.run(BackupManager().cleanup_old_backups())" 2>/dev/null || true
    done
) &

# Start the ASGI server
echo "[TASKHUB] Starting Gunicorn + Uvicorn..."
exec gunicorn -c gunicorn_conf.py -k uvicorn.workers.UvicornWorker bot.main:app
