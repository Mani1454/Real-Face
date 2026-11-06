const {defineConfig} = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser',
  timeout: 30000,
  use: {baseURL: 'http://127.0.0.1:8001', headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined, screenshot: 'only-on-failure'},
  webServer: {
    command: `"${require('node:path').join(__dirname, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')}" -X utf8 -m uvicorn server:app --app-dir code --host 127.0.0.1 --port 8001`,
    url: 'http://127.0.0.1:8001/api/config',
    reuseExistingServer: false,
    env: {DEEPGRAM_API_KEY: '', GROQ_API_KEY: ''},
  },
});
