#!/bin/sh
# unseenet-helpbot in a container (README: "In Docker").
#
#   (no arguments)        unseenet-helpbot run, with /data/helpbot.toml
#   init, run, sync, ask, news ...   that command
#   -h, --help            as unseenet-helpbot
#   sh, python3, unseenet ...   run that program instead
#
# The vault's passphrase: a Docker secret (unseenet_vault_passphrase),
# UNSEENET_VAULT_PASSPHRASE_FILE, or UNSEENET_VAULT_PASSPHRASE. The core starts its own
# Tor; beside a node in compose, set nodes = ["node:1119"] in helpbot.toml. The model's
# address for a new helpbot.toml: HELPBOT_MODEL_URL (compose: http://ollama:11434/v1).
set -eu
DATA=${UNSEENET_DATA:-/data}
CONFIG=${UNSEENET_HELPBOT_CONFIG:-$DATA/helpbot.toml}

# Started as root (the default): make /data ours, then drop root for good.
if [ "$(id -u)" = 0 ]; then
    if [ "$(stat -c %u "$DATA")" != 10001 ]; then
        chown -R unseenet:unseenet "$DATA"
    fi
    chmod 700 "$DATA"
    # A secret file is mounted as it is on the host (often root's, mode 600), so the
    # bot's user may not read it: hand a copy on in /tmp (a tmpfs), readable by it only.
    for f in "${UNSEENET_VAULT_PASSPHRASE_FILE:-}" /run/secrets/unseenet_vault_passphrase; do
        if [ -n "$f" ] && [ -r "$f" ]; then
            (umask 077 && cat "$f" > /tmp/unseenet_vault_passphrase)
            chown unseenet:unseenet /tmp/unseenet_vault_passphrase
            export UNSEENET_VAULT_PASSPHRASE_FILE=/tmp/unseenet_vault_passphrase
            break
        fi
    done
    exec su-exec unseenet "$0" "$@"
fi
export HOME="$DATA"

case "${1:-}" in
    sh|ash|python3|unseenet|unseenet-*) exec "$@" ;;
    -h|--help) exec unseenet-helpbot "$@" ;;
esac

if [ -z "${UNSEENET_VAULT_PASSPHRASE:-}" ]; then
    for f in "${UNSEENET_VAULT_PASSPHRASE_FILE:-}" /run/secrets/unseenet_vault_passphrase; do
        if [ -n "$f" ] && [ -r "$f" ]; then
            UNSEENET_VAULT_PASSPHRASE=$(cat "$f")
            export UNSEENET_VAULT_PASSPHRASE
            break
        fi
    done
fi

if [ ! -f "$CONFIG" ]; then
    sed -e "s#^base_url = .*#base_url = \"${HELPBOT_MODEL_URL:-http://ollama:11434/v1}\"#" \
        /opt/unseenet-helpbot/helpbot.example.toml > "$CONFIG"
    echo "unseenet-helpbot: wrote an example $CONFIG - set the group, run init, then start again." >&2
    exit 64
fi
cd "$DATA"
exec unseenet-helpbot -c "$CONFIG" "${@:-run}"
