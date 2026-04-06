#!/usr/bin/env bash
# ============================================================================
# Bittensor Validator Setup Script — Taoshi Subnet 8
# ============================================================================
# Target: WSL2 Ubuntu (or native Linux)
# Prerequisites: Python 3.10+, pip, curl
#
# This script:
#   1. Installs btcli (Bittensor CLI)
#   2. Creates a coldkey wallet (interactive — will prompt for password)
#   3. Creates a hotkey
#   4. Prints the coldkey address for TAO transfer from Kraken
#   5. Waits for TAO balance
#   6. Registers on Subnet 8
#   7. Stakes TAO
#   8. Generates a systemd service for the validator process
#
# Usage:
#   chmod +x scripts/setup-validator.sh
#   ./scripts/setup-validator.sh
# ============================================================================

set -euo pipefail

# --- Configuration (override via env vars) ---
WALLET_NAME="${STA_WALLET_NAME:-sta_wallet}"
HOTKEY_NAME="${STA_HOTKEY_NAME:-sta_hotkey}"
SUBNET_UID="${STA_SUBNET_UID:-8}"
NETWORK="${STA_BITTENSOR_NETWORK:-finney}"
MIN_STAKE_TAO="${STA_MIN_STAKE_TAO:-100}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[x]${NC} $*" >&2; }

# --- Step 0: Check prerequisites ---
check_prereqs() {
    log "Checking prerequisites..."
    for cmd in python3 pip3 curl; do
        if ! command -v "$cmd" &>/dev/null; then
            err "$cmd is required but not found. Install it first."
            exit 1
        fi
    done
    python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log "Python $python_version found"
}

# --- Step 1: Install btcli ---
install_btcli() {
    if command -v btcli &>/dev/null; then
        btcli_version=$(btcli --version 2>/dev/null || echo "unknown")
        log "btcli already installed: $btcli_version"
        return
    fi

    log "Installing bittensor SDK + btcli..."
    pip3 install --user bittensor

    if ! command -v btcli &>/dev/null; then
        # Try adding local bin to PATH
        export PATH="$HOME/.local/bin:$PATH"
        if ! command -v btcli &>/dev/null; then
            err "btcli not found after install. Add ~/.local/bin to your PATH."
            exit 1
        fi
    fi
    log "btcli installed successfully"
}

# --- Step 2: Create coldkey ---
create_coldkey() {
    wallet_path="$HOME/.bittensor/wallets/$WALLET_NAME"
    if [ -d "$wallet_path/coldkey" ] || [ -f "$wallet_path/coldkey" ]; then
        log "Coldkey '$WALLET_NAME' already exists"
        return
    fi

    log "Creating coldkey '$WALLET_NAME'..."
    warn "You will be prompted to set a password. SAVE IT — this protects your TAO."
    echo ""
    btcli wallet new_coldkey --wallet.name "$WALLET_NAME"
    log "Coldkey created"
}

# --- Step 3: Create hotkey ---
create_hotkey() {
    wallet_path="$HOME/.bittensor/wallets/$WALLET_NAME"
    if [ -d "$wallet_path/hotkeys/$HOTKEY_NAME" ] || [ -f "$wallet_path/hotkeys/$HOTKEY_NAME" ]; then
        log "Hotkey '$HOTKEY_NAME' already exists"
        return
    fi

    log "Creating hotkey '$HOTKEY_NAME'..."
    btcli wallet new_hotkey --wallet.name "$WALLET_NAME" --wallet.hotkey "$HOTKEY_NAME"
    log "Hotkey created"
}

# --- Step 4: Show coldkey address for TAO transfer ---
show_address() {
    log "Wallet addresses:"
    echo ""
    btcli wallet overview --wallet.name "$WALLET_NAME"
    echo ""

    # Extract SS58 address
    coldkey_addr=$(btcli wallet overview --wallet.name "$WALLET_NAME" 2>/dev/null | grep -oP '5[A-HJ-NP-Za-km-z1-9]{47}' | head -1 || true)
    if [ -n "$coldkey_addr" ]; then
        echo ""
        log "Send TAO from Kraken to this coldkey address:"
        echo -e "    ${YELLOW}$coldkey_addr${NC}"
        echo ""
    fi
}

# --- Step 5: Wait for TAO balance ---
wait_for_balance() {
    log "Checking balance..."
    while true; do
        balance_output=$(btcli wallet balance --wallet.name "$WALLET_NAME" --subtensor.network "$NETWORK" 2>/dev/null || true)
        echo "$balance_output"

        # Check if balance is sufficient (rough parse)
        has_balance=$(echo "$balance_output" | grep -oP '[\d.]+' | head -1 || echo "0")
        if [ "$(echo "$has_balance > 0" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
            log "Balance detected: $has_balance TAO"
            break
        fi

        warn "No TAO balance yet. Transfer TAO from Kraken to the address above."
        read -rp "Press Enter to re-check, or Ctrl+C to exit and come back later... "
    done
}

# --- Step 6: Register on Subnet 8 ---
register_subnet() {
    log "Registering on Subnet $SUBNET_UID..."
    warn "This costs a registration fee (~0.1 TAO) and may take a few minutes."
    echo ""
    btcli subnet register \
        --wallet.name "$WALLET_NAME" \
        --wallet.hotkey "$HOTKEY_NAME" \
        --netuid "$SUBNET_UID" \
        --subtensor.network "$NETWORK"
    log "Registration complete"
}

# --- Step 7: Stake TAO ---
stake_tao() {
    log "Staking TAO..."
    warn "Validators need substantial stake for weight-setting authority."
    warn "Recommended: stake most of your TAO, keeping ~1 TAO for fees."
    echo ""
    btcli stake add \
        --wallet.name "$WALLET_NAME" \
        --wallet.hotkey "$HOTKEY_NAME" \
        --subtensor.network "$NETWORK"
    log "Staking complete"
}

# --- Step 8: Generate systemd service ---
generate_systemd() {
    service_file="/tmp/sta-validator.service"
    project_dir="${STA_PROJECT_DIR:-$(pwd)}"

    cat > "$service_file" <<UNIT
[Unit]
Description=STA Bittensor Validator (Subnet $SUBNET_UID)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$project_dir/trading
Environment=STA_BITTENSOR_ENABLED=true
Environment=STA_BITTENSOR_NETWORK=$NETWORK
Environment=STA_BITTENSOR_WALLET_NAME=$WALLET_NAME
Environment=STA_BITTENSOR_HOTKEY=$HOTKEY_NAME
Environment=STA_BITTENSOR_HOTKEY_PATH=$HOME/.bittensor/wallets
Environment=STA_BITTENSOR_SUBNET_UID=$SUBNET_UID
ExecStart=$project_dir/.venv/bin/python -m uvicorn api.app:create_app --host 0.0.0.0 --port 8080 --factory
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

    log "Systemd service file generated at: $service_file"
    echo ""
    echo "To install:"
    echo "  sudo cp $service_file /etc/systemd/system/sta-validator.service"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable --now sta-validator"
    echo ""
    echo "To view logs:"
    echo "  journalctl -u sta-validator -f"
}

# --- Main ---
main() {
    echo ""
    echo "============================================"
    echo " Bittensor Validator Setup — Subnet $SUBNET_UID"
    echo "============================================"
    echo ""

    check_prereqs
    install_btcli
    create_coldkey
    create_hotkey
    show_address

    echo ""
    read -rp "Have you transferred TAO from Kraken? [y/N] " transferred
    if [[ "$transferred" =~ ^[Yy] ]]; then
        wait_for_balance
        register_subnet
        stake_tao
    else
        warn "Skipping registration & staking. Run this script again after transferring TAO."
    fi

    generate_systemd

    echo ""
    log "Setup complete! Next steps:"
    echo "  1. Transfer TAO to your coldkey address (if not done)"
    echo "  2. Register on subnet $SUBNET_UID (if skipped)"
    echo "  3. Stake TAO (if skipped)"
    echo "  4. Install and start the systemd service"
    echo "  5. Monitor: curl http://localhost:8080/api/bittensor/status"
    echo "  6. Monitor: curl http://localhost:8080/api/bittensor/metrics"
    echo ""
}

main "$@"
