@echo off
chcp 65001 >nul
echo 🚀 Deploying TaskHub to VPS...
ssh root@153.75.246.79 "cd /opt/taskhub/taskhub && git fetch origin && git reset --hard origin/main && sqlite3 taskhub.db \"UPDATE settings SET value='{}' WHERE key='game_config';\" 2>nul || true && pm2 restart taskhub-bot"
echo ✅ Deploy complete!
pause
