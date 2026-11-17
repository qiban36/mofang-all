import { fileURLToPath } from 'node:url'
import { defineConfig } from '@playwright/test'

// 本机没有全局 Node：所有依赖 node/npm 的命令都要把便携版目录前置进 PATH，
// 否则 Playwright 拉起的 webServer 会报 "node 不是内部或外部命令"。
const PORTABLE_NODE_DIR = 'c:\\Users\\Lenovo\\Desktop\\mofang-all\\.tools\\node-v26.13.1-win-x64'

/** 给 webServer 的 command 拼上便携 Node 的 PATH */
function withPortableNode(command) {
  if (process.platform !== 'win32') return command
  return `set "PATH=${PORTABLE_NODE_DIR};%PATH%" && ${command}`
}

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    // 本机访问 storage.googleapis.com 超时，官方 Chromium 下载不下来，
    // 所以直接用系统已安装的 Chrome（Edge 也可改成 'msedge'）。
    // 网络恢复后可执行 `npx playwright install chromium` 并删掉这一行。
    channel: 'chrome',
    trace: 'retain-on-failure'
  },
  webServer: [
    {
      // 后端 FastAPI：几何计算服务
      command: withPortableNode('python -m uvicorn main:app --port 8000 --host 127.0.0.1'),
      cwd: fileURLToPath(new URL('../backend', import.meta.url)),
      port: 8000,
      reuseExistingServer: true,
      timeout: 120_000
    },
    {
      // 前端 Vite dev server
      command: withPortableNode('npm run dev'),
      cwd: fileURLToPath(new URL('.', import.meta.url)),
      port: 5173,
      reuseExistingServer: true,
      timeout: 120_000
    }
  ]
})
