#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Group Accountability Bot — VPS setup script (Debian / Ubuntu)
#
# What it does:
#   1. Installs system dependencies (python3, venv, git, ffmpeg, espeak-ng)
#   2. Clones or updates the repository
#   3. Creates a Python virtualenv and installs requirements
#   4. Writes the .env configuration (token + guild id)
#   5. Installs a systemd service so the bot runs 24/7 with auto-restart
#
# Usage:
#   sudo ./scripts/setup_server.sh [DISCORD_BOT_TOKEN] [GUILD_ID]
#   or: DISCORD_BOT_TOKEN=xxx GUILD_ID=yyy sudo -E ./scripts/setup_server.sh
#
# Re-running is safe: it updates an existing install instead of failing.
# =============================================================================

# --- Config ----------------------------------------------------------------
REPO_URL="https://github.com/lenoxspider/group_work.git"
INSTALL_DIR="/opt/group_work"
SERVICE_NAME="groupwork"
RUN_USER="groupwork"

log()  { echo -e "\n\033[1;32m==>\033[0m $*"; }
err()  { echo -e "\033[1;31mERROR:\033[0m $*" >&2; exit 1; }

# --- Root check ------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  err "Run as root (or with sudo)."
fi

# --- Credentials (arg > env > prompt) --------------------------------------
DISCORD_BOT_TOKEN="${1:-${DISCORD_BOT_TOKEN:-}}"
GUILD_ID="${2:-${GUILD_ID:-}}"

if [[ -z "$DISCORD_BOT_TOKEN" ]]; then
  read -rp "Discord bot token: " DISCORD_BOT_TOKEN
fi
if [[ -z "$GUILD_ID" ]]; then
  read -rp "Guild ID (server id, optional): " GUILD_ID
fi
if [[ -z "$DISCORD_BOT_TOKEN" ]]; then
  err "DISCORD_BOT_TOKEN is required."
fi

# --- 1. System dependencies ------------------------------------------------
log "Installing system packages..."
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    python3 python3-venv python3-pip \
    git ca-certificates \
    ffmpeg espeak-ng
else
  err "Unsupported package manager. This script targets Debian/Ubuntu."
fi

# --- 2. Dedicated service user --------------------------------------------
log "Ensuring service user '$RUN_USER'..."
if ! id "$RUN_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$RUN_USER"
fi

# --- 3. Clone or update the repository ------------------------------------
# The install dir is owned by the service user, so allow git (run as root) to
# operate on it. Harmless when re-run.
git config --global --add safe.directory "$INSTALL_DIR" >/dev/null 2>&1 || true

if [[ -d "$INSTALL_DIR/.git" ]]; then
  log "Repository exists — pulling latest..."
  git -C "$INSTALL_DIR" fetch origin
  git -C "$INSTALL_DIR" reset --hard origin/main
else
  log "Cloning repository..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

# --- 4. Virtualenv + dependencies -----------------------------------------
log "Creating virtualenv and installing Python dependencies..."
if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

# --- 5. .env configuration -------------------------------------------------
log "Writing .env..."
cat > "$INSTALL_DIR/.env" <<EOF
DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
GUILD_ID=${GUILD_ID}

TASKS_CHANNEL_NAME=tasks
DEADLINES_CHANNEL_NAME=deadlines
SUBMISSIONS_CHANNEL_NAME=submissions
WALL_OF_SHAME_CHANNEL_NAME=wall-of-shame

DATABASE_PATH=bot_database.sqlite
DEFAULT_TIMEZONE=UTC

# Voice / TTS (espeak-ng). Set true to enable spoken alerts and /say.
TTS_ENABLED=false
TTS_ENGINE=espeak-ng
TTS_BINARY=espeak-ng
TTS_VOICE_DEFAULT=en-us
TTS_DELIVERY=attachment
EOF
chmod 600 "$INSTALL_DIR/.env"

# --- 6. Ownership ----------------------------------------------------------
log "Fixing ownership..."
chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"

# --- 7. systemd service ----------------------------------------------------
log "Installing systemd service '$SERVICE_NAME'..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Group Accountability Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/scripts/run.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# --- 8. Done ---------------------------------------------------------------
log "Setup complete. Bot service: $SERVICE_NAME"
echo "  status:   systemctl status $SERVICE_NAME"
echo "  logs:     journalctl -u $SERVICE_NAME -f"
echo "  restart:  systemctl restart $SERVICE_NAME"
echo "  stop:     systemctl stop $SERVICE_NAME"
echo
echo "Give it a few seconds, then check the logs to confirm it connected."