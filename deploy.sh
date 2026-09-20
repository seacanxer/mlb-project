#!/usr/bin/env bash
# Safe deploy: fail loudly on a dirty tree or non-fast-forward pull
# (incident lesson — never deploy basi). Prints the FC formula version so
# the deployed engine config is visible in deploy logs.
set -e
BRANCH="${1:-main}"
CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
  echo "❌ [Deploy] Branch aktif $CURRENT_BRANCH; target deploy $BRANCH. Checkout target dahulu."
  exit 1
fi

echo "🔍 [Deploy] Checking for a clean tree..."
if [ -n "$(git status --porcelain)" ]; then
  echo "❌ [Deploy] ABORT: working tree is dirty. Commit/stash first."
  exit 1
fi

echo "🚀 [Deploy] Pulling latest code (fast-forward only)..."
git pull --ff-only origin "$BRANCH"

echo "📌 [Deploy] Commit: $(git rev-parse --short HEAD)"
echo "📌 [Deploy] Branch: $BRANCH"
if [ -f betting-machine-fc/config.json ]; then
  echo "📌 [Deploy] FC formula: $(python3 -c "import json;print(json.load(open('betting-machine-fc/config.json')).get('formula',{}).get('version','unknown'))")"
fi

echo "📦 [Deploy] Installing dependencies..."
npm install

echo "🗄️ [Deploy] Generating Prisma Client..."
npx prisma generate

echo "🏗️ [Deploy] Building Next.js application..."
npm run build

echo "✅ [Deploy] Build completed successfully!"
echo "ℹ️  Restart your PM2/systemd process to serve this build."
echo "ℹ️  Verify /api/fc/health ui_version and build_commit after restart."
