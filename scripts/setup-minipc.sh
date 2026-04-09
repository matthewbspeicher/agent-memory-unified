#!/usr/bin/env bash
# ============================================================================
# Mini PC Setup Script — Ubuntu Server 24.04
# ============================================================================
# Run as root (or with sudo) on a fresh Ubuntu Server 24.04 install.
#
# This script:
#   1. Installs Docker Engine + Compose plugin
#   2. Installs Node.js 20 + pm2
#   3. Installs Tailscale
#   4. Configures UFW firewall
#   5. Creates the sta user and project directory
#   6. Installs systemd service for Docker Compose
#   7. Sets up pm2 auto-start for the Taoshi validator
#
# Usage:
#   chmod +x scripts/setup-minipc.sh
#   sudo ./scripts/setup-minipc.sh
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[x]${NC} $*" >&2; }

PROJECT_DIR="/opt/agent-memory-unified"
STA_USER="${STA_USER:-sta}"

# --- Check root ---
if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root (use sudo)."
    exit 1
fi

# --- Step 1: System packages ---
log "Updating system packages..."
apt-get update -qq
apt-get install -y -qq curl git jq bc ca-certificates gnupg lsb-release unattended-upgrades

# --- Step 2: Docker Engine ---
if command -v docker &>/dev/null; then
    log "Docker already installed: $(docker --version)"
else
    log "Installing Docker Engine..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    log "Docker installed: $(docker --version)"
fi

# --- Step 3: Node.js 20 + pm2 ---
if command -v node &>/dev/null && node -v | grep -q "^v20"; then
    log "Node.js 20 already installed: $(node -v)"
else
    log "Installing Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
    log "Node.js installed: $(node -v)"
fi

if command -v pm2 &>/dev/null; then
    log "pm2 already installed: $(pm2 -v)"
else
    log "Installing pm2..."
    npm install -g pm2
    log "pm2 installed: $(pm2 -v)"
fi

# --- Step 4: Python (should ship with Ubuntu 24.04) ---
if command -v python3 &>/dev/null; then
    log "Python already installed: $(python3 --version)"
else
    log "Installing Python 3..."
    apt-get install -y -qq python3 python3-venv python3-pip
fi

# --- Step 5: uv (fast Python package manager) ---
if command -v uv &>/dev/null; then
    log "uv already installed: $(uv --version)"
else
    log "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    log "uv installed"
fi

# --- Step 6: Tailscale ---
if command -v tailscale &>/dev/null; then
    log "Tailscale already installed"
else
    log "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
    log "Tailscale installed. Run 'sudo tailscale up' to authenticate."
fi

# --- Step 7: Create user and project directory ---
if id "$STA_USER" &>/dev/null; then
    log "User '$STA_USER' already exists"
else
    log "Creating user '$STA_USER'..."
    useradd -m -s /bin/bash "$STA_USER"
    usermod -aG docker "$STA_USER"
    log "User '$STA_USER' created and added to docker group"
fi

if [ ! -d "$PROJECT_DIR" ]; then
    log "Creating project directory at $PROJECT_DIR..."
    mkdir -p "$PROJECT_DIR"
    chown "$STA_USER":"$STA_USER" "$PROJECT_DIR"
fi

# --- Step 8: UFW Firewall ---
log "Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh                    # SSH from anywhere (Tailscale + LAN)
ufw allow from 192.168.0.0/16 to any port 8080  # Trading API from LAN
ufw allow from 192.168.0.0/16 to any port 9090  # Prometheus from LAN
ufw allow from 192.168.0.0/16 to any port 3001  # Grafana from LAN
# Tailscale manages its own firewall rules via tailscale0 interface
ufw --force enable
log "UFW configured and enabled"

# --- Step 9: Systemd service for Docker Compose ---
log "Creating systemd service for Docker Compose..."
cat > /etc/systemd/system/sta-trading.service <<'UNIT'
[Unit]
Description=STA Trading Engine Stack (Docker Compose)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/agent-memory-unified
ExecStart=/usr/bin/docker compose -f docker-compose.minipc.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.minipc.yml down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable sta-trading.service
log "Systemd service 'sta-trading' created and enabled"

# --- Step 10: pm2 startup for Taoshi validator ---
log "Configuring pm2 startup for user '$STA_USER'..."
su - "$STA_USER" -c "pm2 startup systemd -u $STA_USER --hp /home/$STA_USER" 2>/dev/null || true
log "pm2 startup configured. After starting the Taoshi validator, run: pm2 save"

# --- Summary ---
echo ""
echo "============================================"
echo " Mini PC Setup Complete"
echo "============================================"
echo ""
log "Installed: Docker, Node.js 20, pm2, Python 3, Tailscale, uv"
log "Firewall: SSH + LAN access to 8080/9090/3001"
log "Systemd: sta-trading.service (auto-starts Docker Compose on boot)"
log "User: $STA_USER (with docker group)"
echo ""
warn "Next steps:"
echo "  1. Run 'sudo tailscale up' to authenticate Tailscale"
echo "  2. Clone repo: su - $STA_USER -c 'git clone <repo-url> $PROJECT_DIR'"
echo "  3. Transfer wallet: scp trading/.env.wallet $STA_USER@minipc:$PROJECT_DIR/trading/"
echo "  4. Reconstruct wallet: bash scripts/reconstruct-wallet-wsl.sh"
echo "  5. Configure trading/.env with Railway Postgres URL"
echo "  6. Start services: systemctl start sta-trading"
echo "  7. Start Taoshi validator: cd taoshi-vanta && ./run.sh ..."
echo "  8. Save pm2 state: pm2 save"
echo ""
