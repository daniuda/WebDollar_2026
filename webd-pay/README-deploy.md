# Deploy webd-pay to Contabo VPS

## Prerequisites
- Contabo VPS S, Ubuntu 22.04 LTS
- SSH key access as ubuntu
- Domain pay.webdollar.cloudns.nz pointing to VPS IP

## Steps

### 1. Initial VPS setup
ssh ubuntu@<VPS_IP>
sudo apt update && sudo apt upgrade -y
sudo apt install -y nginx certbot python3-certbot-nginx python3.11 python3.11-venv git

### 2. Install Node.js v16 (for webd-node)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 16.20.2

### 3. Deploy Node-WebDollar
git clone https://github.com/WebDollarTeam/Node-WebDollar ~/webd-node
cd ~/webd-node && npm install
# Transfer or sync blockchain DB (~14GB) before starting

### 4. Deploy webd-pay
git clone <this-repo> ~/webd-pay
cd ~/webd-pay && python3.11 -m venv venv
source venv/bin/activate && pip install -r requirements.txt
# Edit config.json with correct node_secret and base_url

### 5. Seed address pool
python3 seed_addresses.py addresses.txt

### 6. Install systemd services
sudo cp webd-pay.service /etc/systemd/system/
sudo cp webd-node-pay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable webd-node-pay webd-pay
sudo systemctl start webd-node-pay
# Wait for node to sync (~hours), then:
sudo systemctl start webd-pay

### 7. nginx + SSL
sudo cp nginx-pay.conf /etc/nginx/sites-available/webd-pay
sudo ln -s /etc/nginx/sites-available/webd-pay /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d pay.webdollar.cloudns.nz

### 8. Verify
curl https://pay.webdollar.cloudns.nz/
curl -X POST https://pay.webdollar.cloudns.nz/api/v1/payment/create \
  -H "Content-Type: application/json" -d '{"amount": 1.0}'
