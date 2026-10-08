import { writeFile } from 'node:fs/promises'
import type { Page, WebSocket } from '@playwright/test'
import { expect, test } from './fixtures'

const backendBaseUrl = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`
const apiUrl = (path: string): string => `${backendBaseUrl}${path}`

type JsonObject = Record<string, unknown>

type RealConfig = {
  scriptId: string
  userId: string
  accountName: string
  emulatorId?: string
  emulatorIndex?: string
}
type EmulatorBoundConfig = RealConfig & { emulatorId: string; emulatorIndex: string }

type Operation = {
  emulatorId: string
  index: string
  operate: 'open' | 'close'
}

const requiredVariables = [
  'AUTO_MAS_E2E_TEMPLATE_ROOT',
  'AUTO_MAS_E2E_SCRIPT_ID',
  'AUTO_MAS_E2E_USER_ID',
  'AUTO_MAS_E2E_ACCOUNT_NAME',
] as const

const missingVariables = requiredVariables.filter(name => !process.env[name])

const isRecord = (value: unknown): value is JsonObject =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const readBody = async (response: {
  ok(): boolean
  json(): Promise<unknown>
}): Promise<JsonObject> => {
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  if (!isRecord(body)) throw new Error('真实 E2E 接口返回了无效响应')
  return body
}

const readString = (value: unknown): string | undefined =>
  typeof value === 'string' && value ? value : undefined

const getRealConfig = (): RealConfig => ({
  scriptId: process.env.AUTO_MAS_E2E_SCRIPT_ID!,
  userId: process.env.AUTO_MAS_E2E_USER_ID!,
  accountName: process.env.AUTO_MAS_E2E_ACCOUNT_NAME!,
  ...(process.env.AUTO_MAS_E2E_EMULATOR_ID
    ? { emulatorId: process.env.AUTO_MAS_E2E_EMULATOR_ID }
    : {}),
  ...(process.env.AUTO_MAS_E2E_EMULATOR_INDEX
    ? { emulatorIndex: process.env.AUTO_MAS_E2E_EMULATOR_INDEX }
    : {}),
})

const isAllowedStart = (body: unknown, config: RealConfig): boolean =>
  isRecord(body) &&
  body.mode === 'AutoProxy' &&
  body.taskId === config.scriptId &&
  body.userId == null &&
  body.queueUserIds == null &&
  body.resumeFromScriptId == null &&
  (body.userIds == null ||
    (Array.isArray(body.userIds) && body.userIds.length === 1 && body.userIds[0] === config.userId))

const createOperationObserver = (page: Page, config: RealConfig) => {
  const sockets = new Set<WebSocket>()
  const completedTasks = new Map<string, boolean>()
  let pending:
    | {
        operation: Operation
        resolve: (ok: boolean) => void
        timer: NodeJS.Timeout
      }
    | undefined

  const cancel = () => {
    if (!pending) return
    clearTimeout(pending.timer)
    pending.resolve(false)
    pending = undefined
  }

  const handleFrame = ({ payload }: { payload: string | Buffer }) => {
    let message: unknown
    try {
      message = JSON.parse(typeof payload === 'string' ? payload : payload.toString('utf8'))
    } catch {
      return
    }
    if (!isRecord(message) || !isRecord(message.data)) return
    const data = message.data

    if (message.type === 'task.completed' && typeof message.id === 'string') {
      const scripts = Array.isArray(data.task_info) ? data.task_info : []
      const script = scripts.length === 1 && isRecord(scripts[0]) ? scripts[0] : undefined
      const users = Array.isArray(script?.userList) ? script.userList : []
      completedTasks.set(
        message.id,
        script?.script_id === config.scriptId &&
          users.length === 1 &&
          isRecord(users[0]) &&
          users[0].user_id === config.userId &&
          users[0].status === '完成'
      )
      return
    }
    if (!pending || message.id !== 'EmulatorManager') return
    if (message.type !== 'emulator.operation.finished') return
    if (
      data.emulatorId !== pending.operation.emulatorId ||
      data.index !== pending.operation.index ||
      data.operate !== pending.operation.operate
    ) {
      return
    }

    const ok = data.ok === true
    clearTimeout(pending.timer)
    const resolve = pending.resolve
    pending = undefined
    resolve(ok)
  }

  const onSocket = (socket: WebSocket) => {
    if (new URL(socket.url()).pathname !== '/api/core/ws') return
    sockets.add(socket)
    socket.on('framereceived', handleFrame)
  }
  page.on('websocket', onSocket)

  return {
    accountCompleted: (taskId: string) => completedTasks.get(taskId),
    connected: () => [...sockets].some(socket => !socket.isClosed()),
    cancel,
    dispose: () => {
      cancel()
      page.off('websocket', onSocket)
      for (const socket of sockets) socket.off('framereceived', handleFrame)
    },
    waitFor: (operation: Operation, timeoutMs: number): Promise<boolean> => {
      if (pending) throw new Error('真实 E2E 同时等待多个模拟器操作')
      return new Promise(resolve => {
        const timer = setTimeout(() => {
          pending = undefined
          resolve(false)
        }, timeoutMs)
        pending = { operation, resolve, timer }
      })
    },
  }
}

const getDevice = async (page: Page, config: EmulatorBoundConfig) => {
  const response = await page.request.post(apiUrl('/api/emulator/status'), {
    data: { emulatorId: config.emulatorId },
    timeout: 15_000,
  })
  const body = await readBody(response)
  const elevationRequired =
    typeof body.message === 'string' && /WinError 740|请求的操作需要提升/.test(body.message)
  if (elevationRequired)
    throw new Error('模拟器需要管理员权限，请在管理员 PowerShell 中运行 yarn e2e:real:local')
  expect(body.code).toBe(200)
  const allEmulators = isRecord(body.data) ? body.data : {}
  const emulatorData = allEmulators[config.emulatorId]
  const emulator = isRecord(emulatorData) ? emulatorData : {}
  const device = emulator[config.emulatorIndex]
  const devices = isRecord(device) ? device : {}
  return {
    status: typeof devices.status === 'number' ? devices.status : -1,
  }
}

const waitForTaskTerminal = async (page: Page, taskId: string, timeoutMs: number) => {
  await expect
    .poll(
      async () => {
        const response = await page.request.get(apiUrl(`/api/dispatch/task/${taskId}`), {
          timeout: 15_000,
          maxRetries: 2,
        })
        const body = await readBody(response)
        return body.code === 200 ? String(body.status ?? 'missing') : 'missing'
      },
      { timeout: timeoutMs, intervals: [1000, 2000, 5000] }
    )
    .toMatch(/^(success|error|cancelled)$/)

  const response = await page.request.get(apiUrl(`/api/dispatch/task/${taskId}`), {
    timeout: 15_000,
    maxRetries: 2,
  })
  const body = await readBody(response)
  return readString(body.status) ?? 'missing'
}

const emulatorTag = process.env.AUTO_MAS_E2E_EMULATOR_ID ? '@emulator' : '@script-install'

test.describe(`@real @game-schedule @account ${emulatorTag} real game flow`, () => {
  test.skip(process.env.AUTO_MAS_E2E_REAL !== '1', '需要 AUTO_MAS_E2E_REAL=1')
  test.skip(missingVariables.length > 0, `缺少本机真实 E2E 配置: ${missingVariables.join(', ')}`)

  test('runs one preconfigured account through MAS scheduling and the selected script', async ({
    app,
    page,
  }, testInfo) => {
    test.setTimeout(65 * 60 * 1000)
    const config = getRealConfig()
    const observer = createOperationObserver(page, config)
    let taskId: string | undefined
    let startAttempted = false
    let openedByTest = false
    let finalStatus = 'not-started'
    let cleanupStatus = 'ok'
    let accountCompleted = false
    let stage = 'preflight'
    const startedAt = new Date().toISOString()

    const operate = async (action: Operation['operate'], timeoutMs: number) => {
      if (!config.emulatorId || !config.emulatorIndex) {
        throw new Error('当前脚本未绑定模拟器')
      }
      const operation = observer.waitFor(
        { emulatorId: config.emulatorId, index: config.emulatorIndex, operate: action },
        timeoutMs
      )
      try {
        const response = await page.request.post(apiUrl('/api/emulator/operate'), {
          data: {
            emulatorId: config.emulatorId,
            index: config.emulatorIndex,
            operate: action,
          },
          timeout: 15_000,
        })
        expect((await readBody(response)).code).toBe(200)
        expect(await operation, '模拟器操作未成功完成').toBeTruthy()
      } finally {
        observer.cancel()
      }
    }

    try {
      await app.goto('/scheduler')
      await expect.poll(observer.connected, { timeout: 15_000 }).toBe(true)
      await app.evidence('real-e2e-start')

      const snapshot = await readBody(
        await page.request.get(apiUrl('/api/dispatch/runtime-snapshot'))
      )
      expect(Array.isArray(snapshot.tasks) && snapshot.tasks.length === 0).toBe(true)

      const usersBody = await readBody(
        await page.request.post(apiUrl('/api/scripts/user/get'), {
          data: { scriptId: config.scriptId, userId: null },
        })
      )
      expect(usersBody.code).toBe(200)
      const users = isRecord(usersBody.data) ? usersBody.data : {}
      const user = users[config.userId]
      const info = isRecord(user) && isRecord(user.Info) ? user.Info : {}
      // 全选时 UI 省略 userIds；只接受已隔离为唯一目标账号的配置。
      expect(Object.keys(users).length === 1 && isRecord(user)).toBe(true)
      expect(info.Status === true && info.RemainedDay !== 0).toBe(true)
      expect((readString(info.Name) ?? config.userId) === config.accountName).toBe(true)

      if (config.emulatorId && config.emulatorIndex) {
        const emulatorConfig: EmulatorBoundConfig = {
          ...config,
          emulatorId: config.emulatorId,
          emulatorIndex: config.emulatorIndex,
        }
        const emulatorResponse = await page.request.post(apiUrl('/api/emulator/get'), {
          data: { emulatorId: emulatorConfig.emulatorId },
        })
        const emulatorBody = await readBody(emulatorResponse)
        expect(emulatorBody.code).toBe(200)
        const emulatorData = isRecord(emulatorBody.data) ? emulatorBody.data : {}
        expect(emulatorData[emulatorConfig.emulatorId]).toBeTruthy()

        const before = await getDevice(page, emulatorConfig)
        stage = 'emulator'
        expect([0, 1].includes(before.status), '模拟器需处于稳定的在线或离线状态').toBe(true)
        if (before.status === 1) {
          openedByTest = true
          await operate('open', 5 * 60 * 1000)
        }

        await expect
          .poll(() => getDevice(page, emulatorConfig), {
            timeout: 5 * 60 * 1000,
            intervals: [1000, 2000, 5000],
          })
          .toMatchObject({ status: 0 })
      }

      const taskOptionsResponse = await page.request.post(apiUrl('/api/info/combox/task'))
      stage = 'selection'
      const taskOptionsBody = await readBody(taskOptionsResponse)
      expect(taskOptionsBody.code).toBe(200)
      const taskOptions = Array.isArray(taskOptionsBody.data) ? taskOptionsBody.data : []
      const scriptOption = taskOptions.find(
        item => isRecord(item) && item.value === config.scriptId
      )
      expect(isRecord(scriptOption)).toBeTruthy()
      const scriptLabel = readString(isRecord(scriptOption) ? scriptOption.label : undefined)
      expect(scriptLabel).toBeTruthy()

      await page.locator('.task-control .ant-select').nth(0).click()
      const options = page.locator('.ant-select-dropdown:visible .ant-select-item-option-content')
      await expect(options.first()).toBeVisible()
      const optionLabels = await options.allTextContents()
      const scriptIndex = optionLabels.findIndex(label => label.trim() === scriptLabel)
      expect(scriptIndex >= 0).toBe(true)
      await options.nth(scriptIndex).click()

      const accountRows = page.locator('.queue-scope-group label.ant-checkbox-wrapper')
      await expect(accountRows).toHaveCount(1)
      expect((await accountRows.first().innerText()).trim() === config.accountName).toBe(true)
      await accountRows.first().getByRole('checkbox').check()
      await expect(page.locator('.queue-scope .ant-checkbox-checked')).toHaveCount(1)
      const beforeStart = await readBody(
        await page.request.get(apiUrl('/api/dispatch/runtime-snapshot'))
      )
      expect(Array.isArray(beforeStart.tasks) && beforeStart.tasks.length === 0).toBe(true)

      await page.route('**/api/dispatch/start', async route => {
        let requestBody: unknown
        try {
          requestBody = route.request().postDataJSON()
        } catch {
          requestBody = undefined
        }
        const valid = !startAttempted && isAllowedStart(requestBody, config)
        if (!valid) {
          await route.fulfill({ status: 409, json: { code: 409, status: 'error' } })
          return
        }
        startAttempted = true
        try {
          const response = await route.fetch({ timeout: 30_000, maxRedirects: 0 })
          const body: unknown = await response.json()
          // 先记下任务，后续 UI 或断言失败仍能中止本次真实运行。
          if (isRecord(body)) taskId = readString(body.taskId)
          await route.fulfill({ response })
        } catch {
          await route.fulfill({ status: 502, json: { code: 502, status: 'error' } })
        }
      })
      const startResponsePromise = page
        .waitForResponse(
          response =>
            response.url().includes('/api/dispatch/start') &&
            response.request().method() === 'POST',
          { timeout: 45_000 }
        )
        .catch(() => undefined)
      await page.locator('.task-control .control-row .ant-btn-primary').click()
      stage = 'dispatch'
      const startResponse = await startResponsePromise
      if (!startResponse) throw new Error('真实调度启动请求未完成')
      const startBody = await readBody(startResponse)
      expect(startBody.code).toBe(200)
      expect(Boolean(taskId)).toBe(true)

      finalStatus = 'running'
      finalStatus = await waitForTaskTerminal(page, taskId!, 40 * 60 * 1000)
      expect(finalStatus).toBe('success')
      // 调度器 success 不代表游戏成功；必须核对公开完成事件里的目标账号结果。
      await expect.poll(() => observer.accountCompleted(taskId!), { timeout: 15_000 }).toBe(true)
      accountCompleted = true
      stage = 'completed'
      await expect(page.locator('.tab-status.ant-tag-success')).toBeVisible({ timeout: 30_000 })
      await app.evidence('real-e2e-complete')
    } finally {
      let taskTerminated = !startAttempted
      if (startAttempted && !taskId) cleanupStatus = 'failed'
      if (taskId) {
        try {
          const statusResponse = await page.request.get(apiUrl(`/api/dispatch/task/${taskId}`), {
            timeout: 15_000,
          })
          const statusBody = await readBody(statusResponse)
          if (statusBody.code !== 200) cleanupStatus = 'failed'
          if (statusBody.status === 'running') {
            const stopResponse = await page.request.post(apiUrl('/api/dispatch/stop'), {
              data: { taskId },
              timeout: 30_000,
            })
            const stopBody = await readBody(stopResponse)
            if (stopBody.code !== 200) cleanupStatus = 'failed'
            const stoppedStatus = await waitForTaskTerminal(page, taskId, 90_000)
            if (!['success', 'error', 'cancelled'].includes(stoppedStatus)) {
              cleanupStatus = 'failed'
            } else {
              taskTerminated = true
            }
          } else if (['success', 'error', 'cancelled'].includes(String(statusBody.status))) {
            taskTerminated = true
          } else {
            cleanupStatus = 'failed'
          }
        } catch {
          cleanupStatus = 'failed'
        }
      }

      if (openedByTest && taskTerminated && config.emulatorId && config.emulatorIndex) {
        const emulatorConfig: EmulatorBoundConfig = {
          ...config,
          emulatorId: config.emulatorId,
          emulatorIndex: config.emulatorIndex,
        }
        try {
          const snapshot = await readBody(
            await page.request.get(apiUrl('/api/dispatch/runtime-snapshot'))
          )
          if (!Array.isArray(snapshot.tasks) || snapshot.tasks.length > 0) {
            cleanupStatus = 'failed'
          } else {
            const beforeClose = await getDevice(page, emulatorConfig)
            if (beforeClose.status === 0) {
              await operate('close', 90_000)
              await expect
                .poll(() => getDevice(page, emulatorConfig), { timeout: 90_000 })
                .toMatchObject({ status: 1 })
            } else if (beforeClose.status !== 1) {
              cleanupStatus = 'failed'
            }
          }
        } catch {
          cleanupStatus = 'failed'
        }
      }
      observer.dispose()
      if (!accountCompleted) {
        await app.evidence('real-e2e-failed').catch(() => undefined)
      }
      const summaryPath = testInfo.outputPath('real-e2e-summary.json')
      await writeFile(
        summaryPath,
        JSON.stringify(
          {
            startedAt,
            finishedAt: new Date().toISOString(),
            stage,
            scheduler: finalStatus,
            accountCompleted,
            cleanupStatus,
          },
          null,
          2
        )
      )
      await testInfo.attach('real-e2e-summary.json', {
        path: summaryPath,
        contentType: 'application/json',
      })
      expect.soft(cleanupStatus, '真实 E2E 清理任务或模拟器失败').toBe('ok')
    }
  })
})
