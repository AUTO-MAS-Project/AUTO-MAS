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
  const completedTasks = new Map<string, TaskCompletion>()
  const createdTaskIds = new Set<string>()
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

  const onSocket = (socket: WebSocket) => {
    if (new URL(socket.url()).pathname !== '/api/core/ws') return
    sockets.add(socket)
    socket.on('framereceived', handleFrame)
  }
  page.on('websocket', onSocket)

  return {
    taskCompletion: (taskId: string) => completedTasks.get(taskId),
    createdTaskId: () => [...createdTaskIds][0],
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
  observer: ReturnType<typeof createOperationObserver>,
  timeoutMs: number
) => {
  let status = 'unavailable'
  await expect
    .poll(
      async () => {
        if (observer.taskCompletion(taskId)) return 'event'
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

  test('runs one preconfigured account through MAS scheduling and the selected script', async ({
    app,
    page,
  }, testInfo) => {
    test.setTimeout(65 * 60 * 1000)
    const config = getRealConfig()
    const observer = createOperationObserver(page, config)
    let taskId: string | undefined
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

      // 监听启动请求以记录 taskId，但不拦截（让后端处理幂等性）
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

      // 验证启动请求参数是否符合预期
      let requestBody: unknown
      try {
        requestBody = startResponse.request().postDataJSON()
      } catch {
        throw new Error('无法解析启动请求体')
      }
      if (!isAllowedStart(requestBody, config)) {
        throw new Error(
          `启动请求参数不匹配预期配置: ${JSON.stringify(requestBody)}`
        )
      }

      // 提取 taskId
      const startBody = await readBody(startResponse)
      if (isRecord(startBody)) taskId = readString(startBody.taskId)
      if (!taskId) throw new Error('启动响应缺少 taskId')
      let startBody: JsonObject | undefined
      try {
        startBody = await readBody(startResponse)
      } catch {
        // 启动请求可能已被后端接受但响应在传输中损坏；task.created 仍是公开兜底。
      }
      if (!taskId) {
        await expect
          .poll(() => observer.createdTaskId(), { timeout: 15_000, intervals: [250, 500, 1000] })
          .toBeDefined()
        taskId = observer.createdTaskId()
      }
      expect(startBody?.code ?? 200).toBe(200)
      expect(Boolean(taskId)).toBe(true)

      finalStatus = 'running'
      finalStatus = await waitForTaskTerminal(page, taskId!, 40 * 60 * 1000)
      expect(finalStatus).toBe('success')
      // 调度器 success 不代表游戏成功；必须核对公开完成事件里的目标账号结果。
      await expect.poll(() => observer.taskCompletion(taskId!), { timeout: 15_000 }).toBeDefined()
      completion = observer.taskCompletion(taskId!)
      expect(
        completion?.accepted,
        `目标账号结果未被调度器接受: outcome=${completion?.outcome ?? 'missing'}, ` +
          `scriptStatus=${completion?.scriptStatus ?? 'missing'}, ` +
          `userStatus=${completion?.userStatus ?? 'missing'}`
      ).toBe(true)
      accountResultAccepted = true
      stage = 'completed'
      await expect(page.locator('.tab-status.ant-tag-success')).toBeVisible({ timeout: 30_000 })
      await app.evidence('real-e2e-complete')
    } finally {
      let taskTerminated = !startAttempted
      if (startAttempted && !taskId) taskAndEmulatorCleanupStatus = 'failed'
      if (taskId) {
        completion ??= observer.taskCompletion(taskId)
        try {
          const observedCompletion = Boolean(completion)
          let status: string | undefined
          if (!observedCompletion) {
            try {
              status = await readTaskStatus(page, taskId)
            } catch {
              status = undefined
            }
          }
          if (observedCompletion || (status && terminalTaskStatuses.has(status))) {
            taskTerminated = true
          } else if (status === 'running' || status === 'unavailable' || status === undefined) {
            // stop 是幂等的：即使查询超时或任务刚刚自然结束，也要尝试发出收尾请求。
            try {
              const stopResponse = await page.request.post(apiUrl('/api/dispatch/stop'), {
                data: { taskId },
                timeout: 30_000,
              })
              await readBody(stopResponse)
            } catch {
              // 继续等待完成事件或终态；仅凭 stop 请求本身失败不能判断任务仍在运行。
            }
            try {
              const stoppedStatus = await waitForTaskTermination(page, taskId, observer, 90_000)
              if (stoppedStatus === 'event' || terminalTaskStatuses.has(stoppedStatus)) {
                taskTerminated = true
              } else {
                taskAndEmulatorCleanupStatus = 'failed'
              }
            } catch {
              taskAndEmulatorCleanupStatus = 'failed'
            }
          } else {
            taskAndEmulatorCleanupStatus = 'failed'
          }
        } catch {
          taskAndEmulatorCleanupStatus = 'failed'
        }
      }

      if (taskTerminated) {
        try {
          await waitForRuntimeIdle(page, 90_000)
        } catch {
          taskAndEmulatorCleanupStatus = 'failed'
        }
      }

      if (openedByTest && taskTerminated && config.emulatorId && config.emulatorIndex) {
        const emulatorConfig: EmulatorBoundConfig = {
          ...config,
          emulatorId: config.emulatorId,
          emulatorIndex: config.emulatorIndex,
        }
        try {
          const beforeClose = await getDevice(page, emulatorConfig)
          if (beforeClose.status === 0) {
            await operate('close', 90_000)
            await expect
              .poll(() => getDevice(page, emulatorConfig), { timeout: 90_000 })
              .toMatchObject({ status: 1 })
          } else if (beforeClose.status !== 1) {
            taskAndEmulatorCleanupStatus = 'failed'
          }
        } catch {
          taskAndEmulatorCleanupStatus = 'failed'
        }
      }
      observer.dispose()
      if (!accountResultAccepted) {
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
            accountResultAccepted,
            completion: completion ?? null,
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
})
