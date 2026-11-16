import type { ElectronAPI, InstallStageResult } from '../src/types/electron'
import { expect, test } from './fixtures'

type InitializationProgress = Parameters<ElectronAPI['onInitializationProgress']>[0]

declare global {
  interface Window {
    initializationStartupProbe: {
      progress: InitializationProgress
      finish: (result: InstallStageResult) => void
    }
  }
}

test.describe('@init main-process startup status', () => {
  for (const outcome of ['success', 'failure'] as const) {
    test(`shows starting while the backend is pending, then handles ${outcome}`, async ({
      app,
      page,
    }) => {
      await page.addInitScript(() => {
        Object.defineProperty(window, '__AUTO_MAS_BROWSER_DEV_MODE__', {
          get: () => false,
          set: () => undefined,
        })
        let progressListener: InitializationProgress | undefined
        let ready = false
        let finish!: (result: InstallStageResult) => void
        const startup = new Promise<InstallStageResult>(resolve => {
          finish = result => {
            ready = result.success
            resolve(result)
          }
        })
        window.initializationStartupProbe = {
          progress: value => progressListener?.(value),
          finish: result => finish(result),
        }
        let bridge: ElectronAPI | undefined
        Object.defineProperty(window, 'electronAPI', {
          configurable: true,
          get: () => bridge,
          set: (base: ElectronAPI) => {
            bridge = {
              ...base,
              getRuntimeLaunchMode: async () => ({ mode: 'managed', source: 'default' }),
              getRuntimeInitContext: async () => ({ mode: 'managed', fallbackLogPath: '' }),
              desktopStartupStatus: async () => ({
                runtimeMode: 'managed',
                flowKind: 'update',
                fullInitialization: true,
                state: 'running',
                progress: [
                  {
                    stage: 'dependency',
                    stageIndex: 6,
                    totalStages: 7,
                    progress: 0,
                    status: 'started',
                    message: 'Checking startup environment',
                  },
                ],
              }),
              waitDesktopStartup: () => startup,
              onInitializationProgress: callback => {
                progressListener = callback
              },
              removeInitializationProgressListener: () => {
                progressListener = undefined
              },
              backendStart: () => startup,
              backendStatus: async () => ({ isRunning: ready, runtimeSupervised: true }),
              checkRuntimeBinaryUpdate: async () => ({ status: 'skipped' }),
            }
          },
        })
      })

      await app.goto('/initialization')
      await expect(page.locator('.launch-title')).toHaveText('Checking startup environment')
      await page.evaluate(() => {
        window.initializationStartupProbe.progress({
          stage: 'dependency',
          stageIndex: 6,
          totalStages: 7,
          progress: 100,
          status: 'completed',
          message: '运行环境准备完成',
        })
        window.initializationStartupProbe.progress({
          stage: 'backend',
          stageIndex: 7,
          totalStages: 7,
          progress: 0,
          status: 'started',
          message: '正在启动后端服务...',
        })
      })
      await expect(page.locator('.launch-title')).toHaveText('Starting')
      await expect(page).toHaveURL(/#\/initialization$/)
      await page.locator('.launch-language .ant-select').click()
      await page
        .locator('.ant-select-dropdown:visible')
        .getByText('简体中文', { exact: true })
        .click()
      await expect(page.locator('.launch-title')).toHaveText('正在启动')
      await app.evidence(`backend-starting-${outcome}`)

      await page.evaluate(outcome => {
        window.initializationStartupProbe.finish(
          outcome === 'success'
            ? { success: true }
            : {
                success: false,
                failedStage: 'backend',
                error: 'Backend startup failed for test',
                retryable: true,
              }
        )
      }, outcome)
      if (outcome === 'success') {
        await expect(page).toHaveURL(/#\/home$/)
      } else {
        await expect(
          page.getByText('Backend startup failed for test', { exact: true })
        ).toBeVisible()
        await expect(page.getByRole('button', { name: /^重\s*试$/ })).toBeVisible()
      }
    })
  }
})
