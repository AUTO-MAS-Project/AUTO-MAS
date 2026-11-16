import type { ElectronAPI, InstallStageResult } from '../src/types/electron'
import { expect, test } from './fixtures'

type InitializationProgress = Parameters<ElectronAPI['onInitializationProgress']>[0]

declare global {
  interface Window {
    initializationRecoveryProbe: {
      started: boolean
      progress: InitializationProgress
      finish: () => void
    }
  }
}

test.describe('@init managed recovery progress', () => {
  for (const recovery of ['dependency', 'runtime'] as const) {
    test(
      recovery === 'runtime'
        ? 'reinstalls a missing Runtime before resuming an initialized app'
        : 'shows retry progress after joining a failed main-process startup',
      async ({ app, page }) => {
        const missingRuntime = recovery === 'runtime'
        await page.addInitScript((recovery: 'dependency' | 'runtime') => {
          const missingRuntime = recovery === 'runtime'
          // 运行真实页面，只在 Electron IPC 边界提供受控的失败与进度。
          Object.defineProperty(window, '__AUTO_MAS_BROWSER_DEV_MODE__', {
            get: () => false,
            set: () => undefined,
          })
          let progressListener: InitializationProgress | undefined
          let finish: (() => void) | undefined
          let prepared = false
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
                  mode: 'managed',
                  source: 'default',
                }),
                getRuntimeInitContext: async () => ({
                  mode: 'managed',
                  fallbackLogPath: '',
                }),
                desktopStartupStatus: async () => ({
                  runtimeMode: 'managed',
                  flowKind: missingRuntime ? 'startup' : 'first-run',
                  fullInitialization: !missingRuntime,
                  state: 'failed',
                  progress: [],
                }),
                waitDesktopStartup: async () =>
                  missingRuntime
                    ? {
                        success: false,
                        failedStage: 'backend',
                        error: 'Runtime executable is missing',
                        code: 'RUNTIME_NOT_FOUND',
                        retryable: false,
                        remediation: ['update-desktop', 'contact-support'],
                      }
                    : {
                        success: false,
                        failedStage: 'dependency',
                        error: 'Dependency download interrupted',
                        code: 'MIRROR_EXHAUSTED',
                        retryable: true,
                        remediation: ['retry-other-mirror', 'rebuild-environment'],
                      },
                checkRuntimeBinaryUpdate: async () => ({
                  status: 'skipped',
                }),
                initialize: () => {
                  window.initializationRecoveryProbe.started = true
                  return new Promise<{ success: boolean; completedStages: string[] }>(resolve => {
                    finish = () => {
                      prepared = true
                      resolve({
                        success: true,
                        completedStages: ['python', 'repository', 'dependency'],
                      })
                    }
                  })
                },
                installDependencies: () => {
                  window.initializationRecoveryProbe.started = true
                  return new Promise<InstallStageResult>(resolve => {
                    finish = () => resolve({ success: true })
                  })
                },
                onInitializationProgress: callback => {
                  progressListener = callback
                },
                removeInitializationProgressListener: () => {
                  progressListener = undefined
                },
                backendStatus: async () => ({
                  isRunning: !missingRuntime || prepared,
                  runtimeSupervised: true,
                }),
                backendStart: async () =>
                  missingRuntime && !prepared
                    ? {
                        success: false,
                        code: 'RUNTIME_NOT_FOUND',
                        error: 'Runtime executable is missing',
                        retryable: false,
                      }
                    : { success: true },
              }
            },
          })
        }, recovery)

        await app.goto('/initialization')
        await expect(
          page.getByText(
            missingRuntime ? 'Runtime executable is missing' : 'Dependency download interrupted',
            { exact: true }
          )
        ).toBeVisible()
        await expect(
          page.getByRole('button', { name: 'Rebuild the environment', exact: true })
        ).toHaveCount(missingRuntime ? 0 : 1)
        await expect(page.getByRole('radio')).toHaveCount(0)
        await app.evidence(missingRuntime ? 'runtime-reinstall-action' : 'managed-retry-actions')
        await page.getByRole('button', { name: 'Retry', exact: true }).click()
        await expect
          .poll(() => page.evaluate(() => window.initializationRecoveryProbe.started))
          .toBe(true)
        await page.evaluate(
          missingRuntime =>
            window.initializationRecoveryProbe.progress(
              missingRuntime
                ? {
                    stage: 'python',
                    stageIndex: 2,
                    totalStages: 7,
                    progress: 10,
                    status: 'running',
                    indeterminate: true,
                    message: 'Downloading Runtime v0.1.99',
                    runtimeStage: 'runtime.download',
                    runtimeStatus: 'running',
                    targetVersion: 'v0.1.99',
                    item: 'auto-mas-runtime.exe',
                    current: 610,
                    total: 1000,
                    bytesPerSecond: 128,
                  }
                : {
                    stage: 'dependency',
                    stageIndex: 6,
                    totalStages: 7,
                    progress: 61,
                    status: 'running',
                    message: 'Downloading locked dependencies',
                    runtimeStage: 'dependencies.sync',
                    item: 'dependency.whl',
                    current: 610,
                    total: 1000,
                    bytesPerSecond: 128,
                  }
            ),
          missingRuntime
        )
        if (missingRuntime) {
          await expect(page.locator('.launch-title')).toContainText('v0.1.99')
        } else {
          await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '61')
          await expect(page.locator('.launch-title')).toHaveText('Downloading locked dependencies')
        }
        await expect(page.locator('.launch-details')).toContainText(
          missingRuntime ? 'auto-mas-runtime.exe' : 'dependency.whl'
        )
        await app.evidence(missingRuntime ? 'runtime-reinstall-progress' : 'managed-retry-progress')

        await page.evaluate(() => window.initializationRecoveryProbe.finish())
        await expect(page).toHaveURL(/#\/home$/)
      }
    )
  }
})
