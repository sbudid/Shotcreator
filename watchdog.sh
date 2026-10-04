#!/bin/bash
# Shotcreator API watchdog - pastikan backend selalu jalan
# Dijalankan via cron tiap 2 menit

PORT=${SHOTCREATOR_PORT:-8000}
APPDIR="$HOME/workspace/shotcreator/apps/api"
LOGFILE="/tmp/shotcreator-api.log"

# Cek apakah API respons
if curl -s -m 5 "http://localhost:$PORT/api/health" | grep -q '"ok": true'; then
    exit 0
fi

# Mati/tidak respons -> bunuh sisa proses dan nyalakan lagi
pkill -f "server.py" 2>/dev/null
sleep 2

cd "$APPDIR" || exit 1
# Load env vars (AI config dll)
if [ -f "$HOME/workspace/shotcreator/.env" ]; then
    set -a
    . "$HOME/workspace/shotcreator/.env"
    set +a
fi
nohup python3 server.py > "$LOGFILE" 2>&1 &
echo "[$(date '+%F %T')] watchdog: restarted shotcreator API (port $PORT)" >> "$LOGFILE"
