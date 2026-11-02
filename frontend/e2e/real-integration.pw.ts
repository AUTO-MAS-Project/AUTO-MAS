import { writeFile } from 'node:fs/promises'
import dayjs from 'dayjs'
import type { Page, WebSocketRoute } from '@playwright/test'
import type { HistoryBucket, HistoryIndexItem } from '../src/api'
import { expect, test } from './fixtures'
import { cleanupRealRun } from './real-cleanup'
import { observeMainConnection } from './socket-recovery'

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

type Device = {
  status: number
  adbAddress: string
}

type TaskCompletion = {
  accepted: boolean
  outcome?: string
  scriptStatus?: string
  userStatus?: string
}

const requiredVariables = [
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

const isAllowedStart = (body: unknown, config: RealConfig, queueId: string): boolean => {
  if (!isRecord(body)) return false
  const scope = body.queueUserIds
  const users = isRecord(scope) ? scope[config.scriptId] : undefined
  return (
    body.mode === 'AutoProxy' &&
    body.taskId === queueId &&
    body.userId == null &&
    body.userIds == null &&
    body.resumeFromScriptId == null &&
    (scope == null ||
      (isRecord(scope) &&
        Object.keys(scope).length === 1 &&
        Array.isArray(users) &&
        users.length === 1 &&
        users[0] === config.userId))
  )
}

const createOperationObserver = async (page: Page, config: RealConfig) => {
  const completedTasks = new Map<string, TaskCompletion>()
  const createdTaskIds = new Set<string>()
  const runningAccounts = new Set<string>()
  const taskUpdates = new Map<string, WebSocketRoute>()
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

  const handleFrame = (payload: string | Buffer, route: WebSocketRoute) => {
    let message: unknown
    try {
      message = JSON.parse(typeof payload === 'string' ? payload : payload.toString('utf8'))
    } catch {
      return
    }
    if (!isRecord(message) || !isRecord(message.data)) return
    const data = message.data

    if (
      typeof message.id === 'string' &&
      ['task.info.updated', 'task.log.updated', 'task.completed'].includes(String(message.type))
    ) {
      taskUpdates.set(message.id, route)
    }
    if (message.type === 'task.info.updated' && typeof message.id === 'string') {
      const scripts = Array.isArray(data.task_info) ? data.task_info : []
      const script = scripts.find(
        (item: unknown) => isRecord(item) && item.script_id === config.scriptId
      )
      const users = Array.isArray(script?.userList) ? script.userList : []
      const user = users.find((item: unknown) => isRecord(item) && item.user_id === config.userId)
      if (readString(user?.status)?.startsWith('运行')) runningAccounts.add(message.id)
    }

    if (message.id === 'TaskManager' && message.type === 'task.created') {
      const scripts = Array.isArray(data.scripts) ? data.scripts : []
      if (
        scripts.some((item: unknown) => isRecord(item) && item.scriptId === config.scriptId) &&
        typeof data.taskId === 'string'
      ) {
        createdTaskIds.add(data.taskId)
      }
      return
    }

    if (message.type === 'task.completed' && typeof message.id === 'string') {
      const scripts = Array.isArray(data.task_info) ? data.task_info : []
      const script = scripts.find(
        (item: unknown) => isRecord(item) && item.script_id === config.scriptId
      )
      const users = Array.isArray(script?.userList) ? script.userList : []
      const user = users.find((item: unknown) => isRecord(item) && item.user_id === config.userId)
      const outcome = readString(data.outcome)
      const scriptStatus = readString(script?.status)
      const userStatus = readString(user?.status)
      completedTasks.set(message.id, {
        accepted:
          outcome === 'success' &&
          scriptStatus === '完成' &&
          (userStatus === '完成' || userStatus === '部分失败'),
        outcome,
        scriptStatus,
        userStatus,
      })
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

  const connection = await observeMainConnection(page, handleFrame)

  return {
    taskCompletion: (taskId: string) => completedTasks.get(taskId),
    createdTaskId: () => [...createdTaskIds].at(-1),
    resetCreated: () => createdTaskIds.clear(),
    accountRunning: (taskId: string) => runningAccounts.has(taskId),
    updatedOn: (taskId: string, route: WebSocketRoute) => taskUpdates.get(taskId) === route,
    reconnect: connection.reconnect,
    connected: () => connection.connections.some(socket => !socket.closed),
    cancel,
    dispose: () => {
      cancel()
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

const getDevice = async (page: Page, config: EmulatorBoundConfig): Promise<Device> => {
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
    adbAddress: typeof devices.adb_address === 'string' ? devices.adb_address.trim() : '',
  }
}

const isAdbReady = (device: Device): boolean =>
  device.status === 0 && device.adbAddress.length > 0 && device.adbAddress !== 'Unknown'

const terminalTaskStatuses = new Set(['success', 'error', 'cancelled'])

const readTaskStatus = async (page: Page, taskId: string): Promise<string> => {
  const response = await page.request.get(apiUrl(`/api/dispatch/task/${taskId}`), {
    timeout: 15_000,
    maxRetries: 2,
  })
  if (!response.ok()) return 'unavailable'
  const body = await response.json()
  return isRecord(body) && body.code === 200 ? String(body.status ?? 'missing') : 'missing'
}

const waitForRuntimeIdle = async (page: Page, timeoutMs: number): Promise<void> => {
  await expect
    .poll(
      async () => {
        try {
          const snapshot = await readBody(
            await page.request.get(apiUrl('/api/dispatch/runtime-snapshot'), {
              timeout: 15_000,
              maxRetries: 2,
            })
          )
          return Array.isArray(snapshot.tasks) ? snapshot.tasks.length : -1
        } catch {
          return -1
        }
      },
      { timeout: timeoutMs, intervals: [500, 1000, 2000] }
    )
    .toBe(0)
}

const waitForTaskTerminal = async (page: Page, taskId: string, timeoutMs: number) => {
  let status = 'unavailable'
  await expect
    .poll(
      async () => {
        try {
          status = await readTaskStatus(page, taskId)
        } catch {
          // 真实脚本可能暂时占用后端；把请求错误留给下一轮轮询。
          status = 'unavailable'
        }
        return status
      },
      { timeout: timeoutMs, intervals: [1000, 2000, 5000] }
    )
    .toMatch(/^(success|error|cancelled)$/)

  return status
}

const waitForTaskTermination = async (
  page: Page,
  taskId: string,
  observer: Awaited<ReturnType<typeof createOperationObserver>>,
  timeoutMs: number
) => {
  let status = 'unavailable'
  await expect
    .poll(
      async () => {
        if (observer.taskCompletion(taskId)) {
          status = 'event'
          return status
        }
        try {
          status = await readTaskStatus(page, taskId)
        } catch {
          status = 'unavailable'
        }
        return status
      },
      { timeout: timeoutMs, intervals: [1000, 2000, 5000] }
    )
    .toMatch(/^(event|success|error|cancelled)$/)

  return status
}

const emulatorTag = process.env.AUTO_MAS_E2E_EMULATOR_ID ? '@emulator' : '@script-install'

test.describe(`@real @game-schedule @account ${emulatorTag} real game flow`, () => {
  test.skip(process.env.AUTO_MAS_E2E_REAL !== '1', '需要 AUTO_MAS_E2E_REAL=1')
  test.skip(missingVariables.length > 0, `缺少本机真实 E2E 配置: ${missingVariables.join(', ')}`)

  for (const scenario of ['complete', 'stop-restart'] as const) {
    test(`runs a UI queue with one preconfigured account: ${scenario}`, async ({
      app,
      page,
    }, testInfo) => {
      test.setTimeout(65 * 60 * 1000)
      const config = getRealConfig()
      const observer = await createOperationObserver(page, config)
      let taskId: string | undefined
      let startAttempted = false
      let queueId: string | undefined
      let firstCancelledTask: string | undefined
      let historyVerified = false
      let openedByTest = false
      let finalStatus = 'not-started'
      let taskAndEmulatorCleanupStatus = 'ok'
      let accountResultAccepted = false
      let completion: TaskCompletion | undefined
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
            .poll(async () => isAdbReady(await getDevice(page, emulatorConfig)), {
              timeout: 5 * 60 * 1000,
              intervals: [1000, 2000, 5000],
            })
            .toBe(true)
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

        const goTo = async (name: string) =>
          page
            .getByRole('menuitem')
            .filter({ has: page.getByText(name, { exact: true }) })
            .click()
        const responseFor = (path: string) =>
          page.waitForResponse(
            response => response.url().endsWith(path) && response.request().method() === 'POST'
          )
        await goTo('Queue')
        const createdQueue = responseFor('/api/queue/add')
        await page.getByRole('button', { name: 'New queue' }).click()
        const queueBody = await readBody(await createdQueue)
        expect(queueBody.code).toBe(200)
        queueId = readString(queueBody.queueId)
        expect(queueId).toBeTruthy()
        const queueName = `E2E real ${scenario}`
        await page.locator('.queue-edit-btn').click()
        await page.locator('.queue-title-input').fill(queueName)
        const renamed = responseFor('/api/queue/update')
        await page.locator('.queue-title-input').press('Enter')
        expect((await readBody(await renamed)).code).toBe(200)
        const added = responseFor('/api/queue/item/add')
        await page.getByRole('button', { name: 'Add task' }).click()
        expect((await readBody(await added)).code).toBe(200)
        await page.locator('.queue-item-card .script-select').click()
        const saved = responseFor('/api/queue/item/update')
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(scriptLabel!, { exact: true })
          .click()
        expect((await readBody(await saved)).code).toBe(200)
        await goTo('Scheduler')
        await page.locator('.task-control .ant-select').nth(0).click()
        const options = page.locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        await options.filter({ hasText: queueName }).click()

        // 「本次运行范围」收在浮层里：先展开，再按账号名勾选
        const scopeTrigger = page.locator('.task-control .control-row button:has(.anticon-team)')
        await expect(scopeTrigger).toBeVisible()
        await scopeTrigger.click()
        const scopePanel = page.locator('.ant-popover:visible .queue-scope')
        await expect(scopePanel).toBeVisible()
        const accountRows = scopePanel.locator('.queue-scope-group label.ant-checkbox-wrapper')
        await expect(accountRows).toHaveCount(1)
        expect((await accountRows.first().innerText()).trim() === config.accountName).toBe(true)
        await accountRows.first().getByRole('checkbox').check()
        await expect(scopePanel.locator('.ant-checkbox-checked')).toHaveCount(1)
        // 浮层是 click 触发的，再点一次触发器收起，避免盖住启动按钮
        await scopeTrigger.click()
        await expect(page.locator('.ant-popover:visible .queue-scope')).toHaveCount(0)
        const beforeStart = await readBody(
          await page.request.get(apiUrl('/api/dispatch/runtime-snapshot'))
        )
        expect(Array.isArray(beforeStart.tasks) && beforeStart.tasks.length === 0).toBe(true)

        const historyStart = dayjs().subtract(1, 'day').format('YYYY-MM-DD')
        const readHistory = async () => {
          const body = await readBody(
            await page.request.post(apiUrl('/api/history/search'), {
              data: {
                mode: 'DAILY',
                start_date: historyStart,
                end_date: dayjs().format('YYYY-MM-DD'),
              },
            })
          )
          expect(body.code).toBe(200)
          return body.data as Record<string, Record<string, HistoryBucket>>
        }
        const records = (data: Record<string, Record<string, HistoryBucket>>) =>
          Object.values(data).flatMap(users =>
            Object.values(users).flatMap(bucket => bucket.index ?? [])
          )
        const historyBaseline = new Set(records(await readHistory()).map(record => record.id))
        const scriptBody = await readBody(
          await page.request.post(apiUrl('/api/scripts/get'), {
            data: { scriptId: config.scriptId },
          })
        )
        expect(scriptBody.code).toBe(200)
        const scripts = isRecord(scriptBody.data) ? scriptBody.data : {}
        const script = scripts[config.scriptId]
        const scriptInfo = isRecord(script) && isRecord(script.Info) ? script.Info : {}
        const scriptName = readString(scriptInfo.Name)
        expect(scriptName).toBeTruthy()

        const start = async () => {
          observer.resetCreated()
          taskId = undefined
          // 监听启动请求以记录 taskId，但不拦截（让后端处理幂等性）
          const startResponsePromise = page
            .waitForResponse(
              response =>
                response.url().includes('/api/dispatch/start') &&
                response.request().method() === 'POST',
              { timeout: 45_000 }
            )
            .catch(() => undefined)

          startAttempted = true
          await page.locator('.task-control .control-row .ant-btn-primary').click()
          stage = 'dispatch'
          const startResponse = await startResponsePromise
          if (!startResponse) throw new Error('真实调度启动请求未完成')

          // 验证启动请求参数是否符合预期
          let requestBody: unknown
          try {
            requestBody = startResponse.request().postDataJSON()
          } catch {
            throw new Error('无法解析启动请求体')
          }
          if (!isAllowedStart(requestBody, config, queueId!)) {
            throw new Error('启动请求参数不匹配此次队列与账号')
          }

          // 提取 taskId
          let startBody: JsonObject | undefined
          try {
            startBody = await readBody(startResponse)
            if (isRecord(startBody)) taskId = readString(startBody.taskId)
          } catch {
            // 启动请求可能已被后端接受但响应在传输中损坏；task.created 仍是公开兜底。
          }
          if (!taskId) {
            await expect
              .poll(() => observer.createdTaskId(), {
                timeout: 15_000,
                intervals: [250, 500, 1000],
              })
              .toBeDefined()
            taskId = observer.createdTaskId()
          }
          expect(startBody?.code ?? 200).toBe(200)
          expect(Boolean(taskId)).toBe(true)

          finalStatus = 'running'
          return taskId!
        }
        const waitForAccount = async (id: string) => {
          await expect
            .poll(
              () => {
                if (observer.taskCompletion(id))
                  throw new Error('目标账号尚未进入可操作的执行阶段，任务已结束')
                return observer.accountRunning(id)
              },
              {
                timeout: 10 * 60 * 1000,
                intervals: [500, 1000, 2000],
              }
            )
            .toBe(true)
          await expect(
            page.locator('.task-control').getByRole('button', { name: /Stop$/ })
          ).toBeEnabled()
          const account = page
            .locator('.overview-panel .user-list')
            .getByText(config.accountName, { exact: true })
          if (!(await account.isVisible()))
            await page.locator('.overview-panel .script-header').click()
          await expect(account).toBeVisible()
          await expect(page.locator('.log-panel .view-lines')).not.toHaveText('')
        }
        const stop = async (id: string) => {
          const stopped = responseFor('/api/dispatch/stop')
          await page.locator('.task-control').getByRole('button', { name: /Stop$/ }).click()
          expect((await readBody(await stopped)).code).toBe(200)
          expect(await waitForTaskTerminal(page, id, 90_000)).toBe('cancelled')
          await expect.poll(() => observer.taskCompletion(id)?.outcome).toBe('cancelled')
          await waitForRuntimeIdle(page, 90_000)
          await expect(
            page.locator('.task-control').getByRole('button', { name: /Run$/ })
          ).toBeEnabled()
          await expect(page.locator('.tab-status.ant-tag-success')).toBeVisible()
        }

        await start()
        await waitForAccount(taskId!)
        if (scenario === 'stop-restart') {
          await stop(taskId!)
          firstCancelledTask = taskId
          await app.evidence('real-e2e-cancelled')
          await start()
          expect(taskId).not.toBe(firstCancelledTask)
          await waitForAccount(taskId!)
          await stop(taskId!)
          finalStatus = 'cancelled'
          completion = observer.taskCompletion(taskId!)
          stage = 'restarted-and-cancelled'
          await app.evidence('real-e2e-restarted')
        } else {
          const recovered = await observer.reconnect()
          await expect
            .poll(() => observer.updatedOn(taskId!, recovered.route), {
              timeout: 5 * 60 * 1000,
              intervals: [500, 1000, 2000],
            })
            .toBe(true)
          expect(recovered.received).toBeGreaterThan(0)
          await expect(page.locator('.task-control')).toHaveCount(1)
          finalStatus = await waitForTaskTerminal(page, taskId!, 40 * 60 * 1000)
          expect(finalStatus).toBe('success')
          // 调度器 success 不代表游戏成功；必须核对公开完成事件里的目标账号结果。
          await expect
            .poll(() => observer.taskCompletion(taskId!), { timeout: 15_000 })
            .toBeDefined()
          completion = observer.taskCompletion(taskId!)
          expect(
            completion?.accepted,
            `目标账号结果未被调度器接受: outcome=${completion?.outcome ?? 'missing'}, ` +
              `scriptStatus=${completion?.scriptStatus ?? 'missing'}, ` +
              `userStatus=${completion?.userStatus ?? 'missing'}`
          ).toBe(true)
          accountResultAccepted = true
          stage = 'completed'
          await expect(
            page.locator(
              `.tab-status.ant-tag-${completion?.userStatus === '部分失败' ? 'error' : 'success'}`
            )
          ).toBeVisible({ timeout: 30_000 })
          await app.evidence('real-e2e-complete')
          await waitForRuntimeIdle(page, 90_000)
          const finishedAt = Date.now()
          const newRecords: HistoryIndexItem[] = []
          await expect
            .poll(
              async () => {
                newRecords.splice(
                  0,
                  newRecords.length,
                  ...records(await readHistory()).filter(
                    record =>
                      !historyBaseline.has(record.id) &&
                      record.username === config.accountName &&
                      record.script_name === scriptName &&
                      Date.parse(record.time) >= Date.parse(startedAt) &&
                      Date.parse(record.time) <= finishedAt
                  )
                )
                return newRecords.length
              },
              { timeout: 30_000 }
            )
            .toBeGreaterThan(0)
          const record = newRecords.at(-1)!
          const searched = responseFor('/api/history/search')
          await goTo('History')
          expect((await readBody(await searched)).code).toBe(200)
          // 分组保留游戏日日期，记录显示时间才转换到本地时区。
          const datePanel = page.locator('.date-panel').filter({
            has: page.getByText(record.time.slice(0, 10), { exact: true }),
          })
          await datePanel.locator('.ant-collapse-header').click()
          await datePanel.locator('.user-item').filter({ hasText: config.accountName }).click()
          const detailResponse = page.waitForResponse(
            response =>
              response.url().endsWith('/api/history/detail') &&
              response.request().postDataJSON()?.recordId === record.id
          )
          await page
            .locator('.record-item')
            .filter({ hasText: dayjs(record.time).format('YYYY-MM-DD HH:mm:ss') })
            .click()
          const detail = await readBody(await detailResponse)
          expect(detail.code).toBe(200)
          const data = isRecord(detail.data) ? detail.data : {}
          expect(data.id).toBe(record.id)
          expect(data.log_available).toBe(true)
          const content = readString(data.log_content)
          expect(content).toBeTruthy()
          const logLine = page.locator('.log-modal-content .view-line').first()
          await expect(logLine).not.toHaveText('')
          expect(content!.replace(/\s/g, '')).toContain(
            (await logLine.innerText()).replace(/\s/g, '')
          )
          await expect(page.locator('.log-modal-content .header-info .ant-tag')).toHaveText(
            record.status === 'success' ? 'Done' : 'Failed'
          )
          historyVerified = true
          stage = 'history-verified'
          await app.evidence('real-e2e-history')
        }
      } finally {
        try {
          await cleanupRealRun({
            startAttempted,
            taskId,
            findTask: async () => {
              taskId = observer.createdTaskId()
              if (taskId) return taskId
              const snapshot = await readBody(
                await page.request.get(apiUrl('/api/dispatch/runtime-snapshot'))
              )
              const tasks = Array.isArray(snapshot.tasks) ? snapshot.tasks : []
              const matching = tasks.filter(
                task =>
                  isRecord(task) &&
                  Array.isArray(task.scripts) &&
                  task.scripts.some(
                    (script: unknown) => isRecord(script) && script.scriptId === config.scriptId
                  )
              )
              if (matching.length === 1) taskId = readString(matching[0].taskId)
              return taskId
            },
            terminateTask: async id => {
              completion ??= observer.taskCompletion(id)
              if (observer.taskCompletion(id)) return
              const status = await readTaskStatus(page, id).catch(() => 'unavailable')
              if (terminalTaskStatuses.has(status)) return
              try {
                const stopped = await page.request.post(apiUrl('/api/dispatch/stop'), {
                  data: { taskId: id },
                  timeout: 30_000,
                })
                expect((await readBody(stopped)).code).toBe(200)
              } catch {
                // 停止响应也可能丢失，仍须等待公开终态。
              }
              await waitForTaskTermination(page, id, observer, 90_000)
            },
            waitForIdle: () => waitForRuntimeIdle(page, 90_000),
            closeEmulator: async () => {
              if (!openedByTest || !config.emulatorId || !config.emulatorIndex) return
              const emulatorConfig: EmulatorBoundConfig = {
                ...config,
                emulatorId: config.emulatorId,
                emulatorIndex: config.emulatorIndex,
              }
              const beforeClose = await getDevice(page, emulatorConfig)
              if (beforeClose.status === 0) {
                await operate('close', 90_000)
                await expect
                  .poll(() => getDevice(page, emulatorConfig), { timeout: 90_000 })
                  .toMatchObject({ status: 1 })
              } else {
                expect(beforeClose.status).toBe(1)
              }
            },
          })
        } catch {
          taskAndEmulatorCleanupStatus = 'failed'
        }
        if (queueId && taskAndEmulatorCleanupStatus === 'ok') {
          try {
            const deleted = await page.request.post(apiUrl('/api/queue/delete'), {
              data: { queueId },
            })
            expect((await readBody(deleted)).code).toBe(200)
          } catch {
            taskAndEmulatorCleanupStatus = 'failed'
          }
        }
        observer.dispose()
        if (stage !== 'history-verified' && stage !== 'restarted-and-cancelled') {
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
              scenario,
              scheduler: finalStatus,
              accountResultAccepted,
              completion: completion ?? null,
              firstRunCancelled: Boolean(firstCancelledTask),
              historyVerified,
              taskAndEmulatorCleanupStatus,
            },
            null,
            2
          )
        )
        await testInfo.attach('real-e2e-summary.json', {
          path: summaryPath,
          contentType: 'application/json',
        })
        // 清理失败应硬失败：遗留运行中的任务或模拟器会影响后续测试
        expect(taskAndEmulatorCleanupStatus, '真实 E2E 清理任务或模拟器失败').toBe('ok')
      }
    })
  }
})
