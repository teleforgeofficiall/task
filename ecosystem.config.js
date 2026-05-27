module.exports = {
  apps: [
    {
      name: "taskhub-bot",
      script: "uvicorn",
      args: "bot.main:app --host 0.0.0.0 --port 8000",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
      env: {
        ENVIRONMENT: "production",
      },
    },
  ],
};
