#!/usr/bin/env bash
set -euo pipefail

WALLET_DIR="$HOME/.bittensor/wallets/sta_wallet"
HOTKEY_DIR="$WALLET_DIR/hotkeys"
ENV_FILE="/opt/agent-memory-unified/trading/.env"

mkdir -p "$HOTKEY_DIR"

B64_COLDKEY_PUB=$(grep '^B64_COLDKEY_PUB=' "$ENV_FILE" | cut -d= -f2-)
B64_HOTKEY=$(grep '^B64_HOTKEY=' "$ENV_FILE" | cut -d= -f2-)

echo "$B64_COLDKEY_PUB" | base64 -d > "$WALLET_DIR/coldkeypub.txt"
echo "$B64_HOTKEY" | base64 -d > "$HOTKEY_DIR/sta_hotkey"

chmod 700 "$WALLET_DIR"
chmod 600 "$WALLET_DIR/coldkeypub.txt"
chmod 700 "$HOTKEY_DIR"
chmod 600 "$HOTKEY_DIR/sta_hotkey"

echo "Wallet reconstructed at $WALLET_DIR"
python3 -c "import json; d=json.load(open('$WALLET_DIR/coldkeypub.txt')); print(f'Coldkey: {d[\"ss58Address\"]}')"
python3 -c "import json; d=json.load(open('$HOTKEY_DIR/sta_hotkey')); print(f'Hotkey: {d[\"ss58Address\"]}')"
