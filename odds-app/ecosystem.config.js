module.exports = {
  apps: [
    {
      name: "odds-app",
      script: "python3",
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8000",
      cwd: __dirname,
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
