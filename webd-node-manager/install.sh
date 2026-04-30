#!/bin/bash
# WebDollar Node Manager — install script (Linux/Ubuntu)
set -e

INSTALL_DIR=/opt/webd-node-manager
SERVICE=webd-node-manager

echo "[1/5] Creare director $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"

echo "[2/5] Copiere fișiere..."
sudo cp manager.py dashboard.html "$INSTALL_DIR/"

if [ ! -f "$INSTALL_DIR/config.json" ]; then
  sudo cp config.example.json "$INSTALL_DIR/config.json"
  echo "      !! Completează $INSTALL_DIR/config.json cu token Telegram și credențiale email"
else
  echo "      config.json existent — păstrat neschimbat"
fi

echo "[3/5] Instalare psutil (optional)..."
pip3 install psutil 2>/dev/null && echo "      psutil instalat OK" \
  || echo "      [WARN] psutil indisponibil — CPU/RAM nu vor fi afișate. pip3 install psutil"

echo "[4/5] Creare serviciu systemd..."
sudo tee /etc/systemd/system/${SERVICE}.service > /dev/null << 'EOF'
[Unit]
Description=WebDollar Node Manager
After=network.target

[Service]
WorkingDirectory=/opt/webd-node-manager
ExecStart=/usr/bin/python3 manager.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "[5/5] Activare serviciu..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl restart "$SERVICE"

echo ""
echo "======================================"
echo " WebDollar Node Manager instalat!"
echo " Dashboard: http://localhost:3003"
echo " Logs:      journalctl -u $SERVICE -f"
echo " Config:    $INSTALL_DIR/config.json"
echo "======================================"
