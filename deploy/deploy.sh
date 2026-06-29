#!/bin/bash
set -e
VPS_IP="153.75.246.79"
VPS_PATH="/opt/taskhub/taskhub"
echo "🚀 Deploying TaskHub to VPS..."
ssh "root@$VPS_IP" << 'EOF'
set -e
cd /opt/taskhub/taskhub
echo "📥 Pulling latest code..."
git fetch origin
git reset --hard origin/main
echo "🗑️  Clearing old game config..."
sqlite3 taskhub.db "UPDATE settings SET value='{}' WHERE key='game_config';" 2>/dev/null || \
  mysql -u root -p taskhub -e "UPDATE settings SET value='{}' WHERE \`key\`='game_config';" 2>/dev/null || \
  echo "ℹ️  DB clear skipped (no sqlite3/mysql CLI)"
echo "🔄 Restarting bot..."
pm2 restart taskhub-bot
echo "✅ Deploy complete!"
EOF
