import type { ElectronAPI, InstallStageResult } from '../src/types/electron'
import { expect, test } from './fixtures'

type DependencyProgress = Parameters<ElectronAPI['onDependencyProgress']>[0]

declare global {
  interface Window {
    initializationRecoveryProbe: {
      started: boolean
      progress: (value: unknown) => void
      finish: () => void
    }
  }
}

test.describe('@init managed recovery progress', () => {
  test('shows retry progress after joining a failed main-process startup', async ({
    app,
    page,
  }) => {
    await page.addInitScript(() => {
      // 运行真实页面，只在 Electron IPC 边界提供受控的失败与进度。
      Object.defineProperty(window, '__AUTO_MAS_BROWSER_DEV_MODE__', {
        get: () => false,
        set: () => undefined,
      })
      let progressListener: DependencyProgress | undefined
      let finish: (() => void) | undefined
      window.initializationRecoveryProbe = {
        started: false,
        progress: value => progressListener?.(value),
        finish: () => finish?.(),
      }
      let bridge: ElectronAPI | undefined
      Object.defineProperty(window, 'electronAPI', {
        configurable: true,
        get: () => bridge,
        set: (base: ElectronAPI) => {
          bridge = {
            ...base,
            getRuntimeLaunchMode: async () => ({
              persisted: 'managed',
              mode: 'managed',
              source: 'setting',
            }),
            getRuntimeInitContext: async () => ({
              mode: 'managed',
              fallbackLogPath: '',
              mirrorKeys: { python: [], pip: [], git: [], repository: [], dependency: [] },
            }),
            desktopStartupStatus: async () => ({
              runtimeMode: 'managed',
              flowKind: 'first-run',
              fullInitialization: true,
              state: 'failed',
              progress: [],
            }),
            waitDesktopStartup: async () => ({
              success: false,
              failedStage: 'dependency',
              error: 'Dependency download interrupted',
              code: 'DEPENDENCIES_SYNC_FAILED',
              retryable: true,
              remediation: ['retry'],
            }),
            checkRuntimeBinaryUpdate: async () => ({
              status: 'skipped',
            }),
            initMirrors: async () => ({ success: true }),
            getMirrors: async () => [],
            installDependencies: () => {
              window.initializationRecoveryProbe.started = true
              return new Promise<InstallStageResult>(resolve => {
                finish = () => resolve({ success: true })
              })
            },
            onDependencyProgress: callback => {
              progressListener = callback
            },
            removeDependencyProgressListener: () => {
              progressListener = undefined
            },
            backendStart: async () => ({ success: true }),
          }
        },
      })
    })

    await app.goto('/initialization')
    await expect(page.getByText('Dependency download interrupted', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect
      .poll(() => page.evaluate(() => window.initializationRecoveryProbe.started))
      .toBe(true)
    await page.evaluate(() =>
      window.initializationRecoveryProbe.progress({
        progress: 61,
        status: 'running',
        message: 'Downloading locked dependencies',
        runtimeStage: 'dependencies.sync',
        item: 'dependency.whl',
        current: 610,
        total: 1000,
        bytesPerSecond: 128,
      })
    )
    await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '61')
    await expect(page.locator('.launch-title')).toHaveText('Downloading locked dependencies')
    await expect(page.locator('.launch-details')).toContainText('dependency.whl')
    await app.evidence('managed-retry-progress')

    await page.evaluate(() => window.initializationRecoveryProbe.finish())
    await expect(page).toHaveURL(/#\/home$/)
  })
})
