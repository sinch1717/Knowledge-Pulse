module.exports = {
  apps: [
    {
      name: "knowledge-pulse-api",
      cwd: "/home/ubuntu/knowledge-pulse/backend",
      script: "/home/ubuntu/knowledge-pulse/backend/.venv/bin/uvicorn",
      args: "app.main:app --host 127.0.0.1 --port 8000",
      interpreter: "none",

      autorestart: true,
      watch: false,

      max_memory_restart: "500M",

      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
