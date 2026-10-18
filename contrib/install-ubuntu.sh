#!/bin/bash
# Install the help bot on a fresh Ubuntu machine (amd64 or arm64), e.g. an
# Oracle Always Free Ampere VM:
#
#   sudo GROUP="unseenet.help@<fp>" bash install-ubuntu.sh
#
# It installs Tor and Ollama, pulls the model, makes a user `helpbot` with a
# venv, a checkout of the docs and a vault with a random passphrase, and
# starts two systemd units: the bot, and a daily `git pull` of the docs.
# Running it again updates the bot and keeps the vault, key and state.
set -euo pipefail

GROUP="${GROUP:?set GROUP to the ID of the help group}"
MODEL="${MODEL:-qwen2.5:7b}"
REPO="${REPO:-https://github.com/unseenet/unseenet-helpbot.git}"
HOME_DIR=/home/helpbot
ENV_FILE=/etc/unseenet-helpbot/env

apt-get update -qq
apt-get install -y -qq tor git python3-venv curl zstd >/dev/null
systemctl disable --now tor >/dev/null 2>&1 || true      # the bot starts its own Tor

if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
systemctl enable --now ollama
ollama pull "$MODEL"

id helpbot >/dev/null 2>&1 || useradd -m -s /bin/bash helpbot
sudo -u helpbot bash -s <<EOF
set -e
cd $HOME_DIR
[ -d unseenet ] && git -C unseenet pull -q || git clone -q https://github.com/unseenet/unseenet.git
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade "git+$REPO"
mkdir -p .config/unseenet-helpbot .local/state/unseenet-helpbot
EOF

mkdir -p /etc/unseenet-helpbot
if [ ! -f "$ENV_FILE" ]; then
  echo "UNSEENET_VAULT_PASSPHRASE=$(head -c 32 /dev/urandom | base64 | tr -d '/+=')" > "$ENV_FILE"
fi
chown root:helpbot "$ENV_FILE"; chmod 640 "$ENV_FILE"

CONFIG=$HOME_DIR/.config/unseenet-helpbot/helpbot.toml
if [ ! -f "$CONFIG" ]; then
  cat > "$CONFIG" <<EOF
[bot]
vault = "$HOME_DIR/.config/unseenet-helpbot/helpbot.vault"
group = "$GROUP"
docs = ["$HOME_DIR/unseenet/docs"]
state_file = "$HOME_DIR/.local/state/unseenet-helpbot/state.json"
triggers = ["@helpbot"]
answer_unanswered_after_minutes = 30
max_per_hour = 10
max_per_thread = 3
poll_seconds = 120

[model]
base_url = "http://127.0.0.1:11434/v1"
model = "$MODEL"
timeout = 600
EOF
  chown helpbot:helpbot "$CONFIG"
fi

if [ ! -f $HOME_DIR/.config/unseenet-helpbot/helpbot.vault ]; then
  sudo -u helpbot env "$(cat "$ENV_FILE")" $HOME_DIR/.venv/bin/unseenet-helpbot -c "$CONFIG" init
fi

cat > /etc/systemd/system/unseenet-helpbot.service <<EOF
[Unit]
Description=Unseenet help bot
After=network-online.target ollama.service
Wants=network-online.target

[Service]
User=helpbot
EnvironmentFile=$ENV_FILE
ExecStart=$HOME_DIR/.venv/bin/unseenet-helpbot -c $CONFIG run
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/unseenet-helpbot-docs.service <<EOF
[Unit]
Description=Update the docs the Unseenet help bot answers from

[Service]
Type=oneshot
User=helpbot
ExecStart=/usr/bin/git -C $HOME_DIR/unseenet pull -q
EOF

cat > /etc/systemd/system/unseenet-helpbot-docs.timer <<EOF
[Unit]
Description=Update the help bot's docs daily

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now unseenet-helpbot-docs.timer
systemctl enable unseenet-helpbot
systemctl restart unseenet-helpbot
echo
echo "The help bot runs. Logs: journalctl -u unseenet-helpbot -f"
echo "Back up: $HOME_DIR/.config/unseenet-helpbot/ (vault, config) and $ENV_FILE (passphrase)"
