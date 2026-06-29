$VPS_IP = "153.75.246.79"
$VPS_PATH = "/opt/taskhub/taskhub"
Write-Host "🚀 Deploying TaskHub to VPS..." -ForegroundColor Cyan
ssh "root@${VPS_IP}" @"
cd ${VPS_PATH}
git fetch origin
git reset --hard origin/main
echo '🗑️  Clearing old game config...'
sqlite3 taskhub.db "UPDATE settings SET value='{}' WHERE key='game_config';" 2>/dev/null || true
pm2 restart taskhub-bot
echo '✅ Deploy complete!'
"@
Read-Host "Press Enter to exit"
