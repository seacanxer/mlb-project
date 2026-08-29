# Deploying FC Betting Machine to `fc.texasdrill.me`

This guide explains how to deploy the Football Betting Recommendation Engine and web dashboard to `fc.texasdrill.me`.

---

## 1. Prerequisites on the Server (Ubuntu / Debian VPS)

- **Domain DNS**: Point an `A` record for `fc.texasdrill.me` to your server's public IP address.
- **Python 3.10+**: `sudo apt update && sudo apt install python3 python3-pip python3-venv`
- **Nginx**: `sudo apt install nginx certbot python3-certbot-nginx`
- **Node.js & PM2 (Recommended)**: `npm install -g pm2`

---

## 2. Option A — Deployment with PM2 (Recommended)

1. Clone or copy `betting-machine-fc` to your server (e.g. `/var/www/fc.texasdrill.me`):
   ```bash
   cd /var/www/fc.texasdrill.me
   ```

2. Run the automated deployment script:
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

3. Start and save PM2 processes (Web Server + Background Scanner Worker):
   ```bash
   pm2 start ecosystem.config.js
   pm2 save
   pm2 startup
   ```

---

## 3. Option B — Deployment with Systemd

1. Copy the systemd service file:
   ```bash
   sudo cp fc-betting.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable fc-betting
   sudo systemctl start fc-betting
   ```

2. Check service status:
   ```bash
   sudo systemctl status fc-betting
   ```

---

## 4. Option C — Deployment with Docker & Docker Compose

1. Start container:
   ```bash
   docker compose up -d --build
   ```

2. Check logs:
   ```bash
   docker compose logs -f
   ```

---

## 5. Configuring Nginx & SSL Certificate

1. Link Nginx site configuration:
   ```bash
   sudo cp nginx.conf /etc/nginx/sites-available/fc.texasdrill.me
   sudo ln -sf /etc/nginx/sites-available/fc.texasdrill.me /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

2. Obtain a free Let's Encrypt SSL certificate:
   ```bash
   sudo certbot --nginx -d fc.texasdrill.me
   ```

---

## 6. Verification & Health Monitoring

- Web App: `https://fc.texasdrill.me`
- Health check endpoint: `https://fc.texasdrill.me/api/health`
- Live picks API: `https://fc.texasdrill.me/api/picks`
