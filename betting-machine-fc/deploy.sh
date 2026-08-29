#!/usr/bin/env bash
# ==============================================================================
# Automated Deployment Script for fc.texasdrill.me
# ==============================================================================
set -e

DOMAIN="fc.texasdrill.me"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 [Deploy] Deploying Football Betting Recommendation Engine to $DOMAIN..."
echo "📂 [Deploy] Application directory: $APP_DIR"

# 1. Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "❌ [Deploy] Python 3 is required but not installed."
    exit 1
fi

# 2. Setup virtual environment if not present
if [ ! -d "$APP_DIR/venv" ]; then
    echo "📦 [Deploy] Creating Python virtual environment..."
    python3 -m venv "$APP_DIR/venv"
fi

echo "📦 [Deploy] Installing dependencies..."
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet

# 3. Run validation & unit test suite
echo "🧪 [Deploy] Running mathematical model formula tests..."
"$APP_DIR/venv/bin/python" "$APP_DIR/tests/test_formulas.py"

# 4. Check / initialize data directories
mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/static"

# 5. Restart application process via PM2 or Systemd
if command -v pm2 &> /dev/null; then
    echo "🔄 [Deploy] Reloading via PM2..."
    cd "$APP_DIR"
    pm2 startOrReload ecosystem.config.js
    pm2 save
elif systemctl is-active --quiet fc-betting; then
    echo "🔄 [Deploy] Reloading Systemd service fc-betting..."
    sudo systemctl restart fc-betting
else
    echo "ℹ️  [Deploy] PM2 / Systemd not active yet."
    echo "ℹ️  To start with PM2: pm2 start $APP_DIR/ecosystem.config.js"
    echo "ℹ️  Or run directly: $APP_DIR/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000"
fi

# 6. Nginx setup helper
if [ -d "/etc/nginx/sites-available" ]; then
    if [ ! -f "/etc/nginx/sites-available/$DOMAIN" ]; then
        echo "🌐 [Deploy] Copying Nginx configuration..."
        sudo cp "$APP_DIR/nginx.conf" "/etc/nginx/sites-available/$DOMAIN"
        sudo ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/"
        sudo nginx -t && sudo systemctl reload nginx
        echo "✅ [Deploy] Nginx site enabled for $DOMAIN"
    fi
fi

echo "✨ [Deploy] Deployment finished successfully for $DOMAIN!"
echo "🔗 Local address: http://127.0.0.1:8000"
echo "🌐 Domain URL:    http://$DOMAIN (or https://$DOMAIN with SSL)"
