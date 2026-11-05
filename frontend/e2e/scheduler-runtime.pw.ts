import { expect, test } from './fixtures'

test.describe('@scheduler runtime ownership', () => {
  for (const order of ['ws-first', 'http-first']) {
    test(`keeps early logs across ${order}, navigation, reload and stop`, async ({ app, page }) => {
      const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36184'}`
      const post = async (url: string, data: unknown) => {
        const response = await page.request.post(`${backend}${url}`, { data })
        const result = await response.json()
        expect(result.code).toBe(200)
        return result
      }
      const { queueId } = await post('/api/queue/add', {})
      await post('/api/queue/update', { queueId, data: { Info: { Name: `Runtime ${order}` } } })
      const taskId = `09dd65a9-b3bf-4eba-ace5-${order === 'ws-first' ? '045491299987' : '045491299988'}`
      let alive = false
      let log = ''
      let seq = 0
      let starts = 0
      let snapshots = 0
      let release = () => {}
      const gate = new Promise<void>(resolve => {
        release = resolve
      })
      const tree = {
        info: { name: `Runtime ${order}`, mode: 'AutoProxy', status: 'running', trigger: 'manual' },
        scripts: {
          order: [{ uid: 'script-run', type: 'TaskScriptItem' }],
          data: {
            'script-run': {
              info: { script_id: 'script-config', name: 'Scoped managed task', status: '等待' },
              users: { order: [], data: {} },
            },
          },
        },
      }
      const dispatch = (type: string, data: unknown, id = taskId) =>
        page.evaluate(
          async ({ type, data, id }) => {
            const module = '/src/services/websocket/subscriptions.ts'
            const { dispatchMessage } = await import(module)
            dispatchMessage({ id, type, data })
          },
          { type, data, id }
        )
      const logPanel = page.locator('.log-panel:visible .monaco-editor .view-lines')
      const emitCreated = () =>
        dispatch(
          'task.created',
          {
            taskId,
            taskName: `Runtime ${order}`,
            mode: 'AutoProxy',
            trigger: 'manual',
            scripts: [{ scriptId: 'script-config', scriptType: 'GeneralConfig' }],
          },
          'TaskManager'
        )
      const emitLog = async (text: string, append = true) => {
        log = append ? log + text : text
        seq++
        await dispatch('task.log.updated', { log: text, seq, append, firstLine: 1 })
      }
      await page.route('**/api/dispatch/runtime-snapshot', async route => {
        if (route.request().method() !== 'GET') return route.continue()
        snapshots++
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify({
            tasks: alive
              ? [
                  {
                    taskId,
                    task: tree,
                    mode: 'AutoProxy',
                    trigger: 'manual',
                    scripts: [{ scriptId: 'script-config', scriptType: 'GeneralConfig' }],
                    stopping: false,
                    log,
                    logSeq: seq,
                    logFirstLine: 1,
                  },
                ]
              : [],
          }),
        })
      })
      await page.route('**/api/dispatch/start', async route => {
        if (route.request().method() === 'OPTIONS') return route.continue()
        starts++
        alive = true
        await gate
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify({ code: 200, taskId }),
        })
      })
      await page.route('**/api/dispatch/stop', async route => {
        if (route.request().method() === 'OPTIONS') return route.continue()
        alive = false
        tree.info.status = 'cancelled'
        await dispatch('task.completed', {
          outcome: 'cancelled',
          result: 'FINAL RESULT',
          task: tree,
        })
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify({ code: 200 }),
        })
      })
      let remoteEditorLoads = 0
      await page.route('https://cdn.jsdelivr.net/npm/monaco-editor*/**', route => {
        remoteEditorLoads++
        return route.abort()
      })
      try {
        await app.goto('/scheduler')
        await page.locator('.task-control .ant-select-selector').first().click()
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .filter({ hasText: `Runtime ${order}` })
          .click()
        const start = page.locator('.task-control').getByRole('button', { name: /Run$/ })
        await expect(start).toBeEnabled()
        await start.click()
        await expect.poll(() => starts).toBe(1)
        if (order === 'http-first') {
          release()
          await expect(
            page.locator('.task-control:visible').getByRole('button', { name: /Stop/ })
          ).toBeVisible()
        }
        await emitCreated()
        await dispatch('task.info.updated', tree)
        await emitLog('', false)
        await emitLog('WAITING_FOR_CONFIG_LOCK\n')
        await expect(logPanel).toContainText('WAITING_FOR_CONFIG_LOCK')
        release()
        await expect(
          page.locator('.task-control:visible').getByRole('button', { name: /Stop/ })
        ).toBeVisible()
        await expect(page.locator('.ant-tabs-tab')).toHaveCount(1)
        await expect(logPanel).toContainText('WAITING_FOR_CONFIG_LOCK')
        await expect(page.locator('.overview-panel:visible')).toContainText('Scoped managed task')
        await emitLog('NATIVE_LOG_AFTER_WAIT\n')
        await expect(logPanel).toContainText('WAITING_FOR_CONFIG_LOCK')
        await expect(logPanel).toContainText('NATIVE_LOG_AFTER_WAIT')
        await app.goto('/home')
        await emitLog('LOG_WHILE_PAGE_INACTIVE\n')
        await app.goto('/scheduler')
        await expect(logPanel).toContainText('LOG_WHILE_PAGE_INACTIVE')
        await page.reload()
        await expect(logPanel).toContainText('WAITING_FOR_CONFIG_LOCK')
        await expect(logPanel).toContainText('LOG_WHILE_PAGE_INACTIVE')
        expect(remoteEditorLoads).toBe(0)
        await expect(page.locator('.ant-tabs-tab')).toHaveCount(1)
        const beforeGap = snapshots
        log += 'RECOVERED_GAP\n'
        seq += 2
        await dispatch('task.log.updated', {
          log: 'RECOVERED_GAP\n',
          seq,
          append: true,
          firstLine: 1,
        })
        await expect.poll(() => snapshots).toBe(beforeGap + 1)
        await expect(logPanel).toContainText('RECOVERED_GAP')
        await app.evidence(`scheduler-runtime-${order}`)
        await page.evaluate(async () => {
          const module = '/src/composables/useTheme.ts'
          await (await import(module)).useTheme().setThemeMode('dark')
          await Promise.allSettled(
            document
              .getAnimations()
              .filter(animation => animation.effect?.getComputedTiming().iterations !== Infinity)
              .map(animation => animation.finished)
          )
        })
        await expect(logPanel).toContainText('RECOVERED_GAP')
        await app.evidence(`scheduler-runtime-dark-${order}`)

        await page.locator('.task-control:visible').getByRole('button', { name: /Stop/ }).click()
        await expect(logPanel).toContainText('FINAL RESULT')
        await expect(
          page.locator('.task-control:visible').getByRole('button', { name: /Run$/ })
        ).toBeVisible()
        await app.evidence(`scheduler-runtime-completed-${order}`)
      } finally {
        release()
        await post('/api/queue/delete', { queueId })
      }
    })
  }
})
