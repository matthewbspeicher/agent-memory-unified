#!/bin/bash
set -e

# Setup Bittensor wallet if environment variables are provided
if [ -n "$B64_COLDKEY_PUB" ] && [ -n "$B64_HOTKEY" ]; then
    echo "🔐 Reconstructing Bittensor wallet from environment variables..."
    
    WALLET_DIR="$HOME/.bittensor/wallets/sta_wallet"
    HOTKEY_DIR="$WALLET_DIR/hotkeys"
    
    # Create wallet directories
    mkdir -p "$HOTKEY_DIR"
    
    # Decode and save the coldkey public file
    echo "$B64_COLDKEY_PUB" | base64 -d > "$WALLET_DIR/coldkeypub.txt"
    
    # Decode and save the hotkey file
    echo "$B64_HOTKEY" | base64 -d > "$HOTKEY_DIR/sta_hotkey"
    
    # Secure permissions
    chmod 700 "$WALLET_DIR"
    chmod 600 "$WALLET_DIR/coldkeypub.txt"
    chmod 700 "$HOTKEY_DIR"
    chmod 600 "$HOTKEY_DIR/sta_hotkey"
    
    echo "✅ Wallet reconstruction complete."
else
    echo "ℹ️ No Bittensor wallet environment variables found. Skipping reconstruction."
fi

# Pass control to the main command (e.g., uvicorn)
exec "$@"