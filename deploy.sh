#!/usr/bin/env bash
set -e

echo "🚀 [Deploy] Pulling latest code..."
git pull origin main

echo "📦 [Deploy] Installing dependencies..."
npm install

echo "🗄️ [Deploy] Generating Prisma Client..."
npx prisma generate

echo "🏗️ [Deploy] Building Next.js application..."
npm run build

echo "✅ [Deploy] Build completed successfully!"
echo "ℹ️  Run 'npm run start' or restart your PM2/systemd process."
