#!/usr/bin/env bash
set -euo pipefail

# Deploy backend from uploaded project directory
# Usage:
#   sudo bash deploy_server.sh /root/wiso_golabel

SRC_DIR="${1:-}"
if [[ -z "$SRC_DIR" || ! -d "$SRC_DIR" ]]; then
  echo "Usage: sudo bash deploy_server.sh /path/to/project"
  exit 1
fi

APP_DIR="/opt/wiso-golabel"
DATA_DIR="/var/lib/wiso-golabel"
SERVICE_FILE="/etc/systemd/system/wiso-golabel.service"

install -d -o wiso -g wiso "$APP_DIR"
install -d -o wiso -g wiso "$DATA_DIR"

# Sync code (exclude heavy local artifacts)
rsync -a --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude "*.log" \
  --exclude "wiso_golabel.db*" \
  --exclude "generated/" \
  "$SRC_DIR"/ "$APP_DIR"/

# Ensure app directory is writable by service user after rsync
chown -R wiso:wiso "$APP_DIR" "$DATA_DIR"

# DB is hardcoded in code as <app_dir>/wiso_golabel.db.
# Copy DB separately from source root if present.
if [[ -f "$SRC_DIR/wiso_golabel.db" ]]; then
  cp -f "$SRC_DIR/wiso_golabel.db" "$APP_DIR/wiso_golabel.db"
fi
chown -f wiso:wiso "$APP_DIR/wiso_golabel.db" 2>/dev/null || true

# Python venv and dependencies
sudo -u wiso python3 -m venv "$APP_DIR/.venv"
sudo -u wiso "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u wiso "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R wiso:wiso "$APP_DIR" "$DATA_DIR"

# Environment file
cat >/etc/wiso-golabel.env <<EOF
WISO_APP_DIR=$APP_DIR
WISO_DATA_DIR=$DATA_DIR
WISO_DB_PATH=$APP_DIR/wiso_golabel.db
PYTHONUNBUFFERED=1
EOF
chmod 640 /etc/wiso-golabel.env

# Install service
install -m 644 "$APP_DIR/deploy/systemd/wiso-golabel.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable wiso-golabel
systemctl restart wiso-golabel
systemctl --no-pager --full status wiso-golabel || true

echo '[OK] Deploy finished.'
echo 'Check logs: journalctl -u wiso-golabel -f'
