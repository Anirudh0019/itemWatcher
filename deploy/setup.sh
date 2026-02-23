#!/usr/bin/env bash
#
# ItemWatcher EC2 deployment script
# Target: Ubuntu 24.04 on EC2 t4g.micro (ARM64 / Graviton)
# Usage: sudo bash setup.sh [REPO_URL]
#
set -euo pipefail

INSTALL_DIR="/opt/itemwatcher"
SERVICE_USER="itemwatcher"
REPO_URL="${1:-}"

# ─── Detect OS ───────────────────────────────────────────────────
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
else
    echo "Cannot detect OS. Exiting."
    exit 1
fi

echo "=== ItemWatcher Deployment ==="
echo "Detected OS: $OS_ID"
echo "Install dir: $INSTALL_DIR"
echo ""

# ─── Install system dependencies ────────────────────────────────
echo ">>> Installing system packages..."

if [[ "$OS_ID" == "ubuntu" ]]; then
    apt-get update
    apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip git
    PYTHON="python3.11"
else
    echo "Unsupported OS: $OS_ID. This script targets Ubuntu 24.04."
    exit 1
fi

echo "Python: $($PYTHON --version)"

# ─── Create service user ────────────────────────────────────────
echo ">>> Creating service user '$SERVICE_USER'..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --shell /bin/false --home-dir "$INSTALL_DIR" "$SERVICE_USER"
fi

# ─── Get the code ───────────────────────────────────────────────
echo ">>> Setting up $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

if [[ -n "$REPO_URL" ]]; then
    echo "Cloning from $REPO_URL..."
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        cd "$INSTALL_DIR" && git pull
    else
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
else
    echo "No repo URL provided."
    echo "Copy your project files to $INSTALL_DIR before continuing."
    echo "Example: scp -r ./* ec2-user@host:$INSTALL_DIR/"
    echo ""
    if [[ ! -f "$INSTALL_DIR/pyproject.toml" ]]; then
        echo "ERROR: $INSTALL_DIR/pyproject.toml not found."
        echo "Re-run with: sudo bash setup.sh https://github.com/you/itemwatcher.git"
        echo "Or copy files first, then re-run: sudo bash setup.sh"
        exit 1
    fi
fi

# ─── Create data directory ──────────────────────────────────────
mkdir -p "$INSTALL_DIR/data"

# ─── Set up .env ────────────────────────────────────────────────
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    if [[ -f "$INSTALL_DIR/deploy/.env.example" ]]; then
        cp "$INSTALL_DIR/deploy/.env.example" "$INSTALL_DIR/.env"
        echo ">>> Created .env from template. Edit $INSTALL_DIR/.env to configure."
    fi
fi

# ─── Create venv and install ────────────────────────────────────
echo ">>> Creating virtual environment..."
$PYTHON -m venv "$INSTALL_DIR/.venv"
source "$INSTALL_DIR/.venv/bin/activate"

echo ">>> Installing ItemWatcher..."
pip install --upgrade pip
pip install -e "$INSTALL_DIR"

echo ">>> Installing Playwright Chromium..."
playwright install chromium

# ─── Fix ownership ──────────────────────────────────────────────
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# ─── Install systemd services ───────────────────────────────────
echo ">>> Installing systemd services..."

cp "$INSTALL_DIR/deploy/itemwatcher.service" /etc/systemd/system/itemwatcher.service
cp "$INSTALL_DIR/deploy/itemwatcher-scheduler.service" /etc/systemd/system/itemwatcher-scheduler.service

systemctl daemon-reload

# Enable and start services
systemctl enable itemwatcher.service
systemctl enable itemwatcher-scheduler.service
systemctl start itemwatcher.service
systemctl start itemwatcher-scheduler.service

# ─── Done ────────────────────────────────────────────────────────
echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Services:"
echo "  itemwatcher.service           - Web UI on port 8000"
echo "  itemwatcher-scheduler.service - Price checks every hour"
echo ""
echo "Commands:"
echo "  systemctl status itemwatcher"
echo "  systemctl status itemwatcher-scheduler"
echo "  journalctl -u itemwatcher -f          # web UI logs"
echo "  journalctl -u itemwatcher-scheduler -f # scheduler logs"
echo ""
echo "Config: $INSTALL_DIR/.env"
echo "Database: $INSTALL_DIR/data/data.db"
echo ""
echo "NEXT STEPS:"
echo "  1. Edit $INSTALL_DIR/.env with your email settings (optional)"
echo "  2. Open http://<your-ec2-ip>:8000 in your browser"
echo "  3. Make sure your EC2 security group allows inbound TCP 8000"
echo ""
