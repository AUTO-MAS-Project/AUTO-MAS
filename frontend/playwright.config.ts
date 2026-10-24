import { defineConfig } from '@playwright/test'
import path from 'node:path'

const frontendRoot = __dirname
const repositoryRoot = path.resolve(frontendRoot, '..')
const backendPort = Number(process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174)
const frontendPort = Number(process.env.AUTO_MAS_E2E_FRONTEND_PORT ?? 5174)
const realE2E = process.env.AUTO_MAS_E2E_REAL === '1'
const dataRoot = process.env.AUTO_MAS_E2E_DATA_ROOT
if (!dataRoot) throw new Error('请通过 yarn e2e 或 yarn e2e:real:local 启动测试')
// 每次运行独占自己的产物目录：并行跑、连着跑都不会互相清掉上一份报告
const outputRoot = realE2E ? 'real' : 'browser'
const runTag = process.env.AUTO_MAS_E2E_RUN_TAG?.trim() || 'latest'

const runtimeEnv = Object.fromEntries(
  Object.entries(process.env).filter(([name]) =>
    /^(ALLUSERSPROFILE|APPDATA|CI|COMSPEC|COMPUTERNAME|COMMONPROGRAMFILES(?:\(X86\))?|HOMEDRIVE|HOMEPATH|HOME|LOCALAPPDATA|NUMBER_OF_PROCESSORS|OS|PATH|PATHEXT|PROCESSOR_ARCHITECTURE|PROGRAMDATA|PROGRAMFILES(?:\(X86\))?|SystemRoot|TEMP|TMP|USERDOMAIN|USERNAME|USERPROFILE|WINDIR)$/i.test(
      name
    )
  )
)

const backendEnv = {
  ...runtimeEnv,
  AUTO_MAS_ENV: 'development',
  AUTO_MAS_HTTP_PORT: String(backendPort),
  AUTO_MAS_SUPERVISED: '1',
  AUTO_MAS_SUPERVISED_PORT: String(backendPort),
  AUTO_MAS_E2E: '1',
}

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.pw.ts',
  outputDir: `test-results/${outputRoot}/${runTag}`,
  grepInvert: realE2E ? undefined : /@real/,
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI && !realE2E ? 1 : 0,
  reporter: [
    ['list'],
    [
      'html',
      {
        outputFolder: `playwright-report/${outputRoot}/${runTag}`,
        open: 'never',
      },
    ],
  ],
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    locale: 'en-US',
    screenshot: realE2E ? 'off' : 'only-on-failure',
    trace: realE2E ? 'off' : 'retain-on-failure',
    video: realE2E ? 'off' : 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },
  webServer: [
    {
      command: `uv run --project "${repositoryRoot}" python "${path.join(repositoryRoot, 'main.py')}"`,
      cwd: dataRoot,
      url: `http://127.0.0.1:${backendPort}/api/core/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: backendEnv,
      stdout: realE2E ? 'ignore' : 'pipe',
      stderr: realE2E ? 'ignore' : 'pipe',
    },
    {
      command: `yarn vp dev --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      cwd: frontendRoot,
      url: `http://127.0.0.1:${frontendPort}`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...runtimeEnv,
        AUTO_MAS_HTTP_PORT: String(backendPort),
      },
    },
  ],
})
