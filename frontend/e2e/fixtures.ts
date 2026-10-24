import { test as base, expect, type Page, type TestInfo } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

type App = {
  goto: (route: string) => Promise<void>
  evidence: (name: string, maskSelectors?: string[]) => Promise<void>
}

const attachBackendLog = async (testInfo: TestInfo): Promise<void> => {
  const dataRoot = process.env.AUTO_MAS_E2E_DATA_ROOT
  if (
    !dataRoot ||
    (process.env.AUTO_MAS_E2E_REAL === '1' && process.env.AUTO_MAS_E2E_ATTACH_BACKEND_LOG !== '1')
  )
    return

  const logPath = path.join(dataRoot, 'debug', 'app.log')
  try {
    await fs.access(logPath)
    await testInfo.attach('backend-app.log', { path: logPath, contentType: 'text/plain' })
  } catch {
    // The backend may fail before the logger creates a file; Playwright's own trace is enough.
  }
}

const createApp = (page: Page, testInfo: TestInfo): App => ({
  goto: async (route: string) => {
    const routePath = route.startsWith('/') ? route : `/${route}`
    await page.goto(`/#${routePath}`)
    await expect.poll(() => new URL(page.url()).hash, { timeout: 20_000 }).toBe(`#${routePath}`)
    await expect(page.locator('#app')).toBeVisible()
    const gotIt = page.getByRole('button', { name: 'Got it' })
    if (await gotIt.isVisible().catch(() => false)) await gotIt.click()
  },
  evidence: async (name: string, maskSelectors: string[] = []) => {
    if (process.env.AUTO_MAS_E2E_REAL === '1') {
      maskSelectors = [
        ...maskSelectors,
        '.task-control',
        '.tab-title',
        '.overview-panel-container',
        '.log-panel-container',
        '.queue-scope',
        '.ant-message',
        '.ant-notification',
      ]
    }
    const screenshotPath = testInfo.outputPath(`${name}.png`)
    await page.screenshot({
      path: screenshotPath,
      fullPage: true,
      mask: maskSelectors.map(selector => page.locator(selector)),
    })
    await testInfo.attach(name, { path: screenshotPath, contentType: 'image/png' })
  },
})

export const test = base.extend<{ app: App }>({
  app: async ({ page }, use, testInfo) => {
    await page.addInitScript(() => {
      ;(window as Window & { __AUTO_MAS_E2E__?: boolean }).__AUTO_MAS_E2E__ = true
    })
    await page.route('**/api/info/notice/get', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          status: 'success',
          message: '',
          ifNeedShow: false,
          data: {},
        }),
      })
    })
    await page.route('**/api/info/*/activity', route => route.abort())
    await use(createApp(page, testInfo))
    await attachBackendLog(testInfo)
  },
})

export { expect }
