#!/bin/bash
# ============================================
# TempMail Bot — Server Deployment Script
# ============================================
# 
# Usage:
#   1. Get a VPS (Ubuntu 22.04+ recommended)
#   2. SSH into your server:  ssh root@YOUR_SERVER_IP
#   3. Upload this project:   scp -r ~/Desktop/project/WiFuX root@YOUR_SERVER_IP:/opt/tempmail/
#   4. Run this script:       bash /opt/tempmail/deploy.sh
#
# That's it! The bot will run 24/7 and auto-restart on crashes.
# ============================================

set -e

echo "========================================"
echo "  📧 TempMail Bot — Deploying ..."
echo "========================================"

# Install Python & pip
echo "[1/5] Installing Python ..."
apt update -y
apt install -y python3 python3-pip python3-venv

# Create virtual environment
echo "[2/5] Setting up virtual environment ..."
cd /opt/tempmail
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "[3/5] Installing dependencies ..."
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv
pip install "python-telegram-bot[job-queue]"

# Create systemd service
echo "[4/5] Creating systemd service ..."
cat > /etc/systemd/system/tempmail-bot.service << 'EOF'
[Unit]
Description=TempMail Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tempmail
ExecStart=/opt/tempmail/venv/bin/python /opt/tempmail/mailmanager.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Environment
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/opt/tempmail/.env

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
echo "[5/5] Starting bot service ..."
systemctl daemon-reload
systemctl enable tempmail-bot
systemctl start tempmail-bot

echo ""
echo "========================================"
echo "  ✅ Bot deployed successfully!"
echo "========================================"
echo ""
echo "  Useful commands:"
echo "    Status  : systemctl status tempmail-bot"
echo "    Logs    : journalctl -u tempmail-bot -f"
echo "    Restart : systemctl restart tempmail-bot"
echo "    Stop    : systemctl stop tempmail-bot"
echo ""
