import { execFile } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import { promisify } from 'node:util'
import {
  _electron as electron,
  type ElectronApplication,
  type Page,
  type TestInfo,
} from '@playwright/test'
import { test, expect } from './fixtures'

type WindowEvent = { name: string; visible: boolean; minimized: boolean; trayCount: number }
type WindowSnapshot = {
  appPath: string
  userData: string
  visible: boolean
  minimized: boolean
  maximized: boolean
  trayCount: number
  events: WindowEvent[]
}
declare global {
  var windowBehaviorE2E: {
    snapshot(): WindowSnapshot
    failTrayIcon(value: boolean): void
    dispose(): Promise<void>
  }
}
type LaunchOptions = {
  launchArgument?: '--auto-start' | '--scheduled-wakeup'
  legacyToTray?: boolean
  silent?: boolean
  maximized?: boolean
  confirmBeforeClose?: boolean
  lastCloseAction?: 'quit' | 'tray'
}

const frontendRoot = path.resolve(__dirname, '..')
const snapshot = (application: ElectronApplication) =>
  application.evaluate(() => globalThis.windowBehaviorE2E.snapshot())

async function withDesktop(
  options: LaunchOptions,
  testInfo: TestInfo,
  verify: (application: ElectronApplication, page: Page, root: string) => Promise<void>
): Promise<void> {
  const runRoot = process.env.AUTO_MAS_E2E_DATA_ROOT
  if (!runRoot || process.env.AUTO_MAS_E2E_IN_PLACE === '1') {
    throw new Error('窗口验证只能使用 run.mjs 的临时数据根')
  }
  const root = await fs.mkdtemp(path.join(runRoot, 'window-behavior-'))
  await fs.mkdir(path.join(root, 'config'))
  await fs.writeFile(
    path.join(root, 'config/frontend_config.json'),
    JSON.stringify({
      language: 'en-US',
      themeMode: 'light',
      confirmBeforeClose: options.confirmBeforeClose ?? true,
      lastCloseAction: options.lastCloseAction ?? 'tray',
      desktopMascotEnabled: false,
      UI: {
        IfToTray: options.legacyToTray ?? true,
        IfShowTray: false,
        IfHideCloseButton: false,
        maximized: options.maximized ?? false,
        location: '100,100',
        size: '1200,900',
      },
      Start: { IfMinimizeDirectly: options.silent ?? false, IfSelfStart: false },
      Update: { IfAutoUpdate: false },
      Function: { IfEnableTelemetry: false },
    })
  )
  // 只准备本次窗口的缓存，不复制作者配置；后端由 run.mjs 独立管理。
  await fs.writeFile(
    path.join(root, 'config/setting.yaml'),
    'Function:\n  IfEnableTelemetry: false\n'
  )
  const environment: Record<string, string> = {
    ...Object.fromEntries(
      Object.entries(process.env).filter(
        (entry): entry is [string, string] =>
          entry[1] !== undefined && entry[0] !== 'ELECTRON_RUN_AS_NODE'
      )
    ),
    AUTO_MAS_E2E: '1',
    AUTO_MAS_WINDOW_E2E_ROOT: root,
    AUTO_MAS_HTTP_PORT: process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174',
    VITE_DEV_SERVER_URL: `http://127.0.0.1:${process.env.AUTO_MAS_E2E_FRONTEND_PORT ?? '5174'}`,
  }
  let application: ElectronApplication | undefined
  try {
    application = await electron.launch({
      args: [
        path.join(__dirname, 'fixtures/window-main.cjs'),
        '--connect-existing-backend',
        ...(options.launchArgument ? [options.launchArgument] : []),
      ],
      env: environment,
    })
    const page = await application.firstWindow()
    await expect
      .poll(async () =>
        (await snapshot(application!)).events.some(event => event.name === 'loaded')
      )
      .toBe(true)
    await expect(page.locator('.minimize-button')).toBeVisible({ timeout: 30000 })
    const state = await snapshot(application)
    expect(state.appPath).toBe(path.join(root, 'frontend'))
    expect(path.relative(root, state.userData).startsWith('..')).toBe(false)
    expect(state.events[0]).toMatchObject({ name: 'created', visible: false })
    await verify(application, page, root)
  } finally {
    if (application) {
      try {
        const evidencePath = testInfo.outputPath('electron-window-events.json')
        await fs.writeFile(evidencePath, JSON.stringify(await snapshot(application), null, 2))
        await testInfo.attach('electron-window-events', {
          path: evidencePath,
          contentType: 'application/json',
        })
      } finally {
        try {
          await application.evaluate(() => globalThis.windowBehaviorE2E.dispose())
        } finally {
          await application.close()
        }
      }
    }
  }
}

test.describe('@window actual Electron main', () => {
  test.beforeAll(async () => {
    await promisify(execFile)(
      process.execPath,
      [path.join(frontendRoot, 'node_modules/typescript/bin/tsc'), '-p', 'tsconfig.electron.json'],
      { cwd: frontendRoot, windowsHide: true }
    )
  })
  for (const scenario of [
    { name: '手动启动且静默开启仍显示', silent: true, visible: true },
    {
      name: '自动启动且静默关闭仍显示',
      launchArgument: '--auto-start',
      silent: false,
      visible: true,
    },
    {
      name: '静默自启及崩溃恢复始终隐藏，聚焦后仍最大化',
      launchArgument: '--auto-start',
      silent: true,
      visible: false,
    },
    {
      name: '定时唤醒静默启动及崩溃恢复始终隐藏，聚焦后仍最大化',
      launchArgument: '--scheduled-wakeup',
      legacyToTray: false,
      silent: true,
      visible: false,
    },
  ] as const) {
    test(scenario.name, async () => {
      await withDesktop(
        { ...scenario, maximized: true },
        test.info(),
        async (application, _page, root) => {
          const state = await snapshot(application)
          expect(state.visible).toBe(scenario.visible)
          expect(state.minimized).toBe(false)
          if (scenario.visible) {
            expect(state.events.some(event => event.name === 'show')).toBe(true)
            await expect.poll(async () => (await snapshot(application)).maximized).toBe(true)
          } else {
            expect(state.events.filter(event => event.name === 'show')).toEqual([])
            expect(state.events.every(event => !event.visible)).toBe(true)
            const startupEvidence = test.info().outputPath('silent-startup-before-focus.json')
            await fs.writeFile(startupEvidence, JSON.stringify(state, null, 2))
            await test.info().attach('silent-startup-before-focus', {
              path: startupEvidence,
              contentType: 'application/json',
            })
            expect(state.trayCount).toBe(1)
            expect(state.events.some(event => event.name === 'tray-created')).toBe(true)
            expect(
              JSON.parse(await fs.readFile(path.join(root, 'config/frontend_config.json'), 'utf8'))
                .UI.maximized
            ).toBe(true)

            const loadedCount = state.events.filter(event => event.name === 'loaded').length
            await application.evaluate(({ BrowserWindow }) =>
              BrowserWindow.getAllWindows()[0]!.webContents.forcefullyCrashRenderer()
            )
            await expect
              .poll(
                async () =>
                  (await snapshot(application)).events.filter(event => event.name === 'loaded')
                    .length
              )
              .toBeGreaterThan(loadedCount)
            // Page/CDP 在崩溃后保持失效；Electron 恢复后仍使用原 webContents。
            await expect
              .poll(
                () =>
                  application.evaluate(({ BrowserWindow }) =>
                    BrowserWindow.getAllWindows()[0]!.webContents.executeJavaScript(
                      "Boolean(document.querySelector('.minimize-button'))"
                    )
                  ),
                { timeout: 30000 }
              )
              .toBe(true)
            const recovered = await snapshot(application)
            expect(recovered).toMatchObject({ visible: false, minimized: false, trayCount: 1 })
            expect(recovered.events.filter(event => event.name === 'show')).toEqual([])

            await application.evaluate(({ BrowserWindow }) =>
              BrowserWindow.getAllWindows()[0]!.webContents.executeJavaScript(
                'window.electronAPI.windowFocus()'
              )
            )
            await expect
              .poll(async () => {
                const current = await snapshot(application)
                return current.visible && current.maximized
              })
              .toBe(true)
          }
        }
      )
    })
  }

  test('旧 IfToTray 不改变标题栏及原生最小化，恢复保留最大化', async () => {
    await withDesktop({ maximized: true }, test.info(), async (application, page) => {
      for (const source of ['titlebar', 'native']) {
        const hideCount = (await snapshot(application)).events.filter(
          event => event.name === 'hide'
        ).length
        if (source === 'titlebar') await page.locator('.minimize-button').click()
        else
          await application.evaluate(({ BrowserWindow }) =>
            BrowserWindow.getAllWindows()[0]!.minimize()
          )
        await expect.poll(async () => (await snapshot(application)).minimized).toBe(true)
        const state = await snapshot(application)
        expect(state.events.filter(event => event.name === 'hide')).toHaveLength(hideCount)
        expect(state.trayCount).toBe(0)
        await page.evaluate(() => window.electronAPI.windowFocus())
        await expect
          .poll(async () => {
            const current = await snapshot(application)
            return current.visible && !current.minimized && current.maximized
          })
          .toBe(true)
      }
    })
  })

  test('原生关闭遵守 lastCloseAction，经真实关闭确认进入托盘', async () => {
    await withDesktop(
      { confirmBeforeClose: true, lastCloseAction: 'tray' },
      test.info(),
      async (application, page) => {
        await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]!.close())
        const prompt = page.locator('.app-close-prompt-modal')
        await expect(prompt).toBeVisible()
        await expect(prompt.locator('input[value=tray]')).toBeChecked()
        expect((await snapshot(application)).visible).toBe(true)
        await prompt.getByRole('button', { name: 'Confirm', exact: true }).click()
        await expect.poll(async () => (await snapshot(application)).visible).toBe(false)
        const state = await snapshot(application)
        expect(state.trayCount).toBe(1)
        const hide = state.events.findIndex(event => event.name === 'hide')
        expect(hide).toBeGreaterThan(state.events.findIndex(event => event.name === 'tray-created'))
        expect(state.events[hide]?.trayCount).toBe(1)
        await page.evaluate(() => window.electronAPI.windowFocus())
        await expect.poll(async () => (await snapshot(application)).visible).toBe(true)
      }
    )
  })

  test('托盘创建失败时原生关闭保持窗口并恢复确认', async () => {
    await withDesktop(
      { confirmBeforeClose: false, lastCloseAction: 'tray' },
      test.info(),
      async (application, page) => {
        await application.evaluate(() => globalThis.windowBehaviorE2E.failTrayIcon(true))
        await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]!.close())
        await expect
          .poll(async () =>
            (await snapshot(application)).events.some(event => event.name === 'tray-failed')
          )
          .toBe(true)
        await expect
          .poll(() =>
            page.evaluate(async () => (await window.electronAPI.loadConfig())?.confirmBeforeClose)
          )
          .toBe(true)
        const state = await snapshot(application)
        expect(state.visible).toBe(true)
        expect(state.minimized).toBe(false)
        expect(state.trayCount).toBe(0)
        expect(state.events.filter(event => event.name === 'hide')).toEqual([])
      }
    )
  })
})
