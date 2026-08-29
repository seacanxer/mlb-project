module.exports = {
  apps: [
    {
      name: 'fc-betting-web',
      script: 'uvicorn',
      args: 'server:app --host 127.0.0.1 --port 8000 --workers 2',
      interpreter: 'python3',
      cwd: __dirname,
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env: {
        PORT: '8000',
        HOST: '127.0.0.1',
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      name: 'fc-betting-worker',
      script: 'worker.py',
      args: '--interval 15',
      interpreter: 'python3',
      cwd: __dirname,
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      env: {
        PYTHONUNBUFFERED: '1',
      },
    },
  ],
};
