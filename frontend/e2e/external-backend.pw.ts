import type { ElectronAPI } from '../src/types/electron'
import { expect, test } from './fixtures'

declare global {
  interface Window {
    recordProcessCommand: (value: string) => Promise<void>
  }
}

test('@init desktop frontend connects without preparing an external backend', async ({
  app,
  page,
}) => {
  const processCommands: string[] = []
  await page.exposeFunction('recordProcessCommand', (command: string) =>
    processCommands.push(command)
  )
  await page.addInitScript(() => {
    Object.defineProperty(window, '__AUTO_MAS_BROWSER_DEV_MODE__', {
      get: () => false,
      set: () => undefined,
    })
    Object.defineProperty(window, 'backendOwnership', { value: 'external' })
    // 上一次更新留下的标记不能让只连接入口安装或更新后端。
    sessionStorage.setItem('forceBackendUpdate', 'true')
    const blocked = async (command: string): Promise<never> => {
      await window.recordProcessCommand(command)
      throw new Error(`External backend cannot be managed: ${command}`)
    }
    let bridge: ElectronAPI | undefined
    Object.defineProperty(window, 'electronAPI', {
      configurable: true,
      get: () => bridge,
      set: (base: ElectronAPI) => {
        bridge = {
          ...base,
          desktopStartupStatus: () => blocked('desktopStartupStatus'),
          getRuntimeInitContext: () => blocked('getRuntimeInitContext'),
          backendStatus: () => blocked('backendStatus'),
          backendStart: () => blocked('backendStart'),
          initialize: () => blocked('initialize'),
          cancelDesktopStartup: () => blocked('cancelDesktopStartup'),
        }
      },
    })
  })
  await app.goto('/initialization')
  await expect(page).toHaveURL(/#\/home$/)
  await expect(page.locator('.home-title')).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => performance.getEntriesByName('启动/业务初始化就绪').length))
    .toBeGreaterThan(0)
  expect(processCommands).toEqual([])
  await app.evidence('external-backend-home')
})
