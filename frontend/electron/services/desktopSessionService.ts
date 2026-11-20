import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { once } from 'node:events'
import { createInterface } from 'node:readline'
import { mkdirSync, appendFileSync, renameSync, statSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { getLocalApiEndpoint } from '../ipc/initializationHandlers'
import { beginMainFeature } from './featureAnalytics'
import { desktopSessionControlToken, setDesktopSessionChildId } from './desktopSessionControl'
import { DESKTOP_SESSION_REPAIRS } from './desktopSessionProtocol'
import type {
  DesktopQueueResult,
  DesktopSessionAvailability,
  DesktopSessionRepair,
  DesktopSessionRequest,
  DesktopSessionSnapshot,
  DesktopSessionStartResult,
} from './desktopSessionProtocol'

type HostEvent = Record<string, unknown> & { event: string }
type RuntimeDescription = { python: string; source: string; root: string; launcher: string }
type StartPrompts = {
  confirmTakeover: () => Promise<boolean>
  notifyEmulatorOnly: (targets: DesktopQueueResult[]) => Promise<void>
  confirmTaskDispatch: (targets: {
    desktop: DesktopQueueResult[]
    main: DesktopQueueResult[]
  }) => Promise<'split' | 'desktop' | 'cancel'>
}
type QueueDispatchPlan = {
  queueIds: string[]
  mainSessionQueueIds?: string[]
  preview: DesktopQueueResult[]
}

class DesktopSessionError extends Error {}

function isRepairPlan(value: unknown): value is DesktopSessionRepair[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    new Set(value).size === value.length &&
    value.every(item => DESKTOP_SESSION_REPAIRS.some(repair => repair === item))
  )
}

const internal = '/internal/desktop-session/'
const header = 'x-mas-desktop-session'

async function request<T>(
  endpoint: string,
  path: string,
  token: string,
  body?: object,
  timeout = 60000
): Promise<T> {
  const response = await fetch(endpoint + path, {
    method: 'POST',
    signal: AbortSignal.timeout(timeout),
    headers: { [header]: token, 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    if (path === internal + 'queues' && response.status === 409) {
      const conflict: { code?: string } | null = await response.json().catch(() => null)
      if (conflict?.code === 'session_changed') throw new DesktopSessionError(conflict.code)
    }
    throw new DesktopSessionError(`http_${response.status}`)
  }
  return (await response.json()) as T
}

export class DesktopSessionService {
  snapshot: DesktopSessionSnapshot = {
    state: 'idle',
    windowState: 'visible',
    checks: [],
    busy: false,
    executing: false,
  }
  private host: ChildProcessWithoutNullStreams | null = null
  private startingHost: Promise<void> | null = null
  private reserved = false
  private orphanedSessionId: number | undefined
  adopted = false
  private hostEvents = new EventTarget()
  private startOperation: Promise<DesktopSessionStartResult> | null = null
  private stopOperation: Promise<void> | null = null
  private repairOperation: Promise<string | undefined> | null = null
  private monitor: NodeJS.Timeout | undefined
  private disconnectPending = false
  private admissionsPaused = false
  private volume = 0
  private logsRoot: string | undefined
  private correlation: string | undefined

  constructor(
    private readonly changed: (snapshot: DesktopSessionSnapshot) => void,
    private readonly requested: (action: 'minimize' | 'close') => void,
    private readonly tasksStarted: (tasks: DesktopQueueResult[]) => void
  ) {}

  get active(): boolean {
    return (
      this.snapshot.busy ||
      this.snapshot.executing ||
      this.orphanedSessionId !== undefined ||
      this.snapshot.sessionId !== undefined ||
      this.snapshot.state === 'connecting' ||
      this.snapshot.state === 'connected'
    )
  }

  get logFolder(): string | undefined {
    return this.logsRoot
  }

  async availability(): Promise<DesktopSessionAvailability> {
    try {
      const runtime = await request<RuntimeDescription>(
        getLocalApiEndpoint(),
        internal + 'describe',
        desktopSessionControlToken,
        undefined,
        5000
      )
      return runtime.launcher ? 'ready' : 'plugin_required'
    } catch (error) {
      return error instanceof DesktopSessionError && error.message === 'http_404'
        ? 'plugin_required'
        : 'unavailable'
    }
  }

  private patch(patch: Partial<DesktopSessionSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch }
    this.changed(this.snapshot)
  }

  private log(event: string, fields: Record<string, unknown> = {}): void {
    if (!this.logsRoot) return
    const path = join(this.logsRoot, 'control.log')
    try {
      mkdirSync(this.logsRoot, { recursive: true })
      if ((statSync(path, { throwIfNoEntry: false })?.size ?? 0) > 2 * 1024 * 1024) {
        rmSync(path + '.1', { force: true })
        renameSync(path, path + '.1')
      }
      appendFileSync(
        path,
        JSON.stringify({
          at: new Date().toISOString(),
          correlation: this.correlation,
          event,
          ...fields,
        }) + '\n'
      )
    } catch {
      // 日志目录不可写时不影响已经受理的业务。
    }
  }

  private ensureHost(): Promise<void> {
    if (this.startingHost) return this.startingHost
    if (this.host) return Promise.resolve()
    this.startingHost = this.spawnHost().finally(() => {
      this.startingHost = null
    })
    return this.startingHost
  }

  private async spawnHost(): Promise<void> {
    const alreadyReserved = this.reserved
    this.reserved = true
    let runtime: RuntimeDescription
    try {
      runtime = await request<RuntimeDescription>(
        getLocalApiEndpoint(),
        internal + 'describe?reserve=true',
        desktopSessionControlToken,
        undefined,
        5000
      )
      if (!runtime.launcher) throw new DesktopSessionError('http_404')
    } catch (error) {
      if (
        !alreadyReserved &&
        error instanceof DesktopSessionError &&
        error.message === 'http_404'
      ) {
        this.reserved = false
        throw new DesktopSessionError('plugin_required')
      }
      throw error
    }
    this.logsRoot = join(runtime.root, 'debug', 'desktop-session')
    const child = spawn(
      runtime.python,
      ['-I', runtime.launcher, runtime.source, 'preview', runtime.root],
      {
        cwd: runtime.source,
        windowsHide: true,
        stdio: 'pipe',
      }
    )
    this.host = child
    const reader = createInterface({ input: child.stdout })
    reader.on('line', line => {
      if (this.host !== child) return
      try {
        this.handleHostEvent(JSON.parse(line) as HostEvent)
      } catch {
        this.log('invalid_host_message')
      }
    })
    // 原生异常有可能携带凭据上下文，诊断只使用宿主协议中的允许字段。
    child.stderr.resume()
    child.stdin.on('error', () => this.log('host_stdin_error'))
    const exited = () => {
      if (this.host !== child) return
      this.host = null
      this.orphanedSessionId ??= this.snapshot.sessionId
      this.log('host_exited', { exitCode: child.exitCode })
      this.hostEvents.dispatchEvent(new Event('exit'))
      if (this.snapshot.closing && this.orphanedSessionId === undefined) return
      this.disconnectPending ||= this.orphanedSessionId !== undefined
      this.patch({ state: this.active ? 'disconnected' : 'idle', code: 'host_exited' })
      this.scheduleMonitor()
    }
    child.once('error', exited)
    child.once('exit', exited)
    try {
      await this.wait(event => event.event === 'ready', 10000)
    } catch (error) {
      if (this.host === child) child.kill()
      throw error
    }
  }

  private handleHostEvent(event: HostEvent): void {
    if (typeof event.correlation === 'string') this.correlation = event.correlation
    if (this.snapshot.closing && event.event === 'state') {
      this.log('host_close_state', { state: event.state })
    }
    if (event.event === 'diagnostics') {
      const checks = event.checks as DesktopSessionSnapshot['checks']
      this.patch({
        checks,
        repairPlan: isRepairPlan(event.repairs) ? event.repairs : [],
        ...(['idle', 'checking', 'blocked'].includes(this.snapshot.state)
          ? { state: checks.some(item => item.required && !item.ok) ? 'blocked' : 'idle' }
          : {}),
      })
    } else if (event.event === 'state') {
      const state = event.state as DesktopSessionSnapshot['state']
      if (state === 'connected') this.adopted = event.adopted === true
      this.patch({
        state:
          state === 'idle' && this.snapshot.checks.some(item => item.required && !item.ok)
            ? 'blocked'
            : state,
        code: event.code as string | undefined,
        sessionId:
          state === 'idle'
            ? undefined
            : ((event.sessionId as number | undefined) ?? this.snapshot.sessionId),
        size:
          state === 'idle'
            ? undefined
            : ((event.size as [number, number] | undefined) ?? this.snapshot.size),
      })
      if (state === 'disconnected') {
        this.disconnectPending = true
        this.scheduleMonitor()
      }
    } else if (event.event === 'window') {
      this.patch({ windowState: event.state as DesktopSessionSnapshot['windowState'] })
    } else if (event.event === 'audio') {
      this.patch({ audioSessions: event.sessions as number })
    } else if (event.event === 'credential_warning') {
      this.patch({ credentialWarning: 'credential_save_failed' })
    } else if (event.event === 'authentication_failure') {
      const { time, status, substatus } = event
      if (
        typeof time === 'string' &&
        Number.isFinite(Date.parse(time)) &&
        typeof status === 'string' &&
        /^0x[0-9A-F]{8}$/.test(status) &&
        typeof substatus === 'string' &&
        /^0x[0-9A-F]{8}$/.test(substatus)
      ) {
        this.patch({ authenticationFailure: { time, status, substatus } })
      }
    } else if (event.event === 'close_requested') {
      this.requested('close')
    } else if (event.event === 'minimize_requested') {
      this.requested('minimize')
    }
    this.hostEvents.dispatchEvent(new CustomEvent('message', { detail: event }))
  }

  private send(message: object): void {
    if (!this.host?.stdin.writable) throw new DesktopSessionError('host_exited')
    this.host.stdin.write(JSON.stringify(message) + '\n')
  }

  private wait(matches: (event: HostEvent) => boolean, timeout: number): Promise<HostEvent> {
    return new Promise((resolve, reject) => {
      const finish = (event?: HostEvent, error?: string) => {
        clearTimeout(timer)
        this.hostEvents.removeEventListener('message', onMessage)
        this.hostEvents.removeEventListener('exit', onExit)
        if (event) resolve(event)
        else reject(new DesktopSessionError(error))
      }
      const onMessage = (event: Event) => {
        const message = (event as CustomEvent<HostEvent>).detail
        if (matches(message)) finish(message)
      }
      const onExit = () => finish(undefined, 'host_exited')
      const timer = setTimeout(() => finish(undefined, 'operation_timeout'), timeout)
      this.hostEvents.addEventListener('message', onMessage)
      this.hostEvents.addEventListener('exit', onExit)
    })
  }

  private exchange(message: object, matches: (event: HostEvent) => boolean, timeout: number) {
    const received = this.wait(matches, timeout)
    try {
      this.send(message)
    } catch (error) {
      this.hostEvents.dispatchEvent(new Event('exit'))
      void received.catch(() => undefined)
      throw error
    }
    return received
  }

  async check(): Promise<DesktopSessionSnapshot> {
    if (this.snapshot.closing) return this.snapshot
    if (!this.active || this.snapshot.state === 'blocked') {
      this.patch({ state: 'checking', code: undefined })
    }
    try {
      await this.ensureHost()
      if (!this.snapshot.closing) {
        const event = await this.exchange(
          { action: 'check' },
          event =>
            event.event === 'diagnostics' ||
            (event.event === 'command_error' && event.action === 'check'),
          30000
        )
        if (event.event === 'command_error') throw new DesktopSessionError('host_unavailable')
      }
    } catch (error) {
      this.patch({
        state: this.snapshot.state === 'checking' ? 'blocked' : this.snapshot.state,
        code: error instanceof DesktopSessionError ? error.message : 'host_unavailable',
      })
    }
    return this.snapshot
  }

  repair(approved: unknown): Promise<string | undefined> {
    const plan = this.snapshot.repairPlan
    if (this.active || this.snapshot.closing) return Promise.resolve('busy')
    if (
      this.snapshot.state !== 'blocked' ||
      !plan ||
      !isRepairPlan(approved) ||
      approved.length !== plan.length ||
      !plan.every(item => approved.includes(item))
    ) {
      return Promise.resolve('environment_changed')
    }
    this.patch({ busy: true, code: undefined })
    this.repairOperation = this.repairInternal(approved).finally(() => {
      this.repairOperation = null
      this.patch({ busy: false })
    })
    return this.repairOperation
  }

  private async repairInternal(
    approvedRepairs: DesktopSessionRepair[]
  ): Promise<string | undefined> {
    const operation = beginMainFeature('desktop_session_environment_repair_finished')
    let code: string | undefined
    try {
      await this.ensureHost()
      const event = await this.exchange(
        { action: 'repair', approvedRepairs },
        event =>
          event.event === 'repair_finished' ||
          (event.event === 'command_error' && event.action === 'repair'),
        180000
      )
      if (event.event === 'command_error') code = 'environment_repair_failed'
      else if (typeof event.code === 'string') code = event.code
    } catch (error) {
      code = error instanceof DesktopSessionError ? error.message : 'environment_repair_failed'
    }
    operation.finish({
      outcome: code === 'environment_repair_cancelled' ? 'cancelled' : code ? 'failure' : 'success',
    })
    if (code) this.patch({ code })
    return code
  }

  start(
    input: DesktopSessionRequest,
    owner: bigint,
    bounds: [number, number, number, number],
    prompts?: StartPrompts
  ): Promise<DesktopSessionStartResult> {
    if (this.snapshot.busy || this.snapshot.closing || this.stopOperation) {
      return Promise.resolve({ code: 'busy', queues: [] })
    }
    this.patch({
      busy: true,
      code: undefined,
      credentialWarning: undefined,
      authenticationFailure: undefined,
    })
    this.startOperation = this.startInternal(input, owner, bounds, prompts).finally(() => {
      this.startOperation = null
      this.patch({ busy: false })
      this.scheduleMonitor()
    })
    return this.startOperation
  }

  private async startInternal(
    input: DesktopSessionRequest,
    owner: bigint,
    bounds: [number, number, number, number],
    prompts?: StartPrompts
  ): Promise<DesktopSessionStartResult> {
    let connection:
      | ReturnType<typeof beginMainFeature<'desktop_session_connection_finished'>>
      | undefined
    const dispatches = new Map<string, ReturnType<typeof beginMainFeature<'task_start_result'>>>()
    let publishingConnection = false
    try {
      const plan = input.queueIds.length
        ? await this.prepareQueueDispatch(input.queueIds, prompts)
        : undefined
      if (input.queueIds.length && !plan?.queueIds.length) {
        return { queues: plan?.preview ?? [] }
      }
      if (this.snapshot.state !== 'connected') {
        connection = beginMainFeature('desktop_session_connection_finished')
      }
      await this.ensureHost()
      if (this.snapshot.state !== 'connected') {
        if (this.snapshot.state === 'disconnected' || this.orphanedSessionId !== undefined) {
          await this.stopTasksAndCloseViewer()
        }
        publishingConnection = true
        await this.updateParentScope(null, true)
        const connect = (adoptSessionId?: number) =>
          this.exchange(
            {
              action: 'connect',
              resolution: input.resolution,
              mode: input.mode,
              password: input.password,
              owner: owner.toString(),
              bounds,
              adoptSessionId,
            },
            event =>
              (event.event === 'state' && event.state !== 'connecting') ||
              (event.event === 'command_error' && event.action === 'connect'),
            120000
          )
        let event = await connect()
        const existing = event.existingSessionId
        if (
          event.code === 'existing_child_session' &&
          typeof existing === 'number' &&
          Number.isInteger(existing) &&
          existing > 0 &&
          prompts
        ) {
          await this.closeViewer({ logoff: false })
          if (!(await prompts.confirmTakeover()))
            throw new DesktopSessionError('takeover_cancelled')
          await this.updateParentScope(null, true)
          event = await connect(existing)
        }
        if (event.state !== 'connected') {
          throw new DesktopSessionError(
            typeof event.code === 'string' && event.event === 'state'
              ? event.code
              : 'connection_failed'
          )
        }
        const sessionId = this.snapshot.sessionId
        if (sessionId === undefined) throw new DesktopSessionError('session_changed')
        await this.updateParentScope(sessionId)
        publishingConnection = false
        this.changeVolume(this.volume)
        connection?.finish({ outcome: 'success', reason_kind: 'none' })
      }
      if (!plan) return { queues: [] }
      if (this.snapshot.state !== 'connected') throw new DesktopSessionError('session_changed')
      const mainIds = new Set(plan.mainSessionQueueIds)
      for (const id of plan.queueIds) {
        dispatches.set(id, beginMainFeature('task_start_result'))
      }
      if (plan.queueIds.some(id => !mainIds.has(id))) this.patch({ executing: true })
      const result = await request<{ results: DesktopQueueResult[] }>(
        getLocalApiEndpoint(),
        internal + 'queues',
        desktopSessionControlToken,
        { queueIds: plan.queueIds, mainSessionQueueIds: plan.mainSessionQueueIds }
      )
      const dispatched = result.results.map(target =>
        mainIds.has(target.queueId) ? { ...target, executionSession: 'main' as const } : target
      )
      for (const queue of dispatched) {
        dispatches.get(queue.queueId)?.finish({
          source: 'desktop_session',
          mode: 'AutoProxy',
          target_kind: queue.targetKind,
          outcome: queue.taskId ? 'accepted' : 'failure',
        })
        dispatches.delete(queue.queueId)
        this.log('queue_admission', {
          queueId: queue.queueId,
          taskId: queue.taskId,
          accepted: Boolean(queue.taskId),
        })
      }
      const accepted = dispatched.filter(target => target.taskId)
      if (accepted.length) this.tasksStarted(accepted)
      const byId = new Map(dispatched.map(target => [target.queueId, target]))
      return {
        queues: plan.preview.length
          ? plan.preview.map(target => byId.get(target.queueId) ?? target)
          : dispatched,
      }
    } catch (error) {
      const code = error instanceof DesktopSessionError ? error.message : 'desktop_session_failed'
      if (publishingConnection) {
        try {
          await this.closeViewer()
        } catch {
          this.log('process_scope_cleanup_failed')
        }
      }
      const reason = code.startsWith('environment_')
        ? 'environment'
        : /password|credential|account|authentication/.test(code)
          ? 'credentials'
          : /rdp|connection|timeout/.test(code)
            ? 'connection'
            : 'process'
      const cancelled = code === 'environment_repair_cancelled' || code === 'takeover_cancelled'
      connection?.finish({ outcome: cancelled ? 'cancelled' : 'failure', reason_kind: reason })
      this.patch({ code })
      this.log(cancelled ? 'start_cancelled' : 'start_failed', { code })
      return { code, queues: [] }
    } finally {
      for (const operation of dispatches.values()) {
        operation.finish({
          source: 'desktop_session',
          mode: 'AutoProxy',
          target_kind: 'unknown',
          outcome: 'failure',
        })
      }
      delete input.password
    }
  }

  async previewQueues(queueIds: string[]): Promise<DesktopQueueResult[]> {
    const { results } = await request<{ results: DesktopQueueResult[] }>(
      getLocalApiEndpoint(),
      internal + 'queues',
      desktopSessionControlToken,
      { queueIds, previewOnly: true }
    )
    return results
  }

  private async prepareQueueDispatch(
    queueIds: string[],
    prompts?: StartPrompts
  ): Promise<QueueDispatchPlan | undefined> {
    if (!prompts) return { queueIds, preview: [] }
    const preview = await this.previewQueues(queueIds)
    const desktop = preview.filter(target => !target.code)
    const main = preview.filter(target => target.code === 'emulator_required')
    if (!desktop.length) {
      if (main.length) await prompts.notifyEmulatorOnly(main)
      return { queueIds: [], preview }
    }
    const choice = main.length ? await prompts.confirmTaskDispatch({ desktop, main }) : 'desktop'
    if (choice === 'cancel') return
    return {
      queueIds: preview
        .filter(
          target => !target.code || (choice === 'split' && target.code === 'emulator_required')
        )
        .map(target => target.queueId),
      mainSessionQueueIds: choice === 'split' ? main.map(target => target.queueId) : undefined,
      preview,
    }
  }

  private async updateParentScope(sessionId: number | null, connecting = false): Promise<void> {
    setDesktopSessionChildId(sessionId)
    await request(
      getLocalApiEndpoint(),
      internal + 'process-scope',
      desktopSessionControlToken,
      {
        sessionId,
        connecting,
      },
      5000
    )
  }

  private scheduleMonitor(): void {
    clearTimeout(this.monitor)
    if (
      (this.disconnectPending || this.snapshot.executing || this.snapshot.state === 'connected') &&
      !this.snapshot.closing
    ) {
      this.monitor = setTimeout(() => void this.monitorExecution(), 1000)
    }
  }

  private async monitorExecution(): Promise<void> {
    if (this.startOperation || this.stopOperation || this.snapshot.closing) return
    const monitor = this.monitor
    try {
      if (this.disconnectPending) {
        await this.stopTasks()
        this.patch({ code: 'executor_interrupted' })
      } else {
        const { idle } = await request<{ idle: boolean }>(
          getLocalApiEndpoint(),
          internal + 'state',
          desktopSessionControlToken,
          undefined,
          2000
        )
        if (
          this.monitor === monitor &&
          !this.startOperation &&
          !this.admissionsPaused &&
          this.snapshot.executing === idle
        ) {
          this.patch({ executing: !idle })
        }
      }
    } catch {
      // 后端暂时不可用时保留执行状态，重试确认任务是否已收尾。
    } finally {
      this.scheduleMonitor()
    }
  }

  private stopTasks(): Promise<void> {
    if (this.stopOperation) return this.stopOperation
    this.stopOperation = (async () => {
      if (this.disconnectPending) await this.updateParentScope(null)
      const { idle } = await request<{ idle: boolean }>(
        getLocalApiEndpoint(),
        internal + 'stop',
        desktopSessionControlToken
      )
      if (!idle) throw new DesktopSessionError('executor_failed')
      this.disconnectPending = false
      this.patch({ executing: false })
    })().finally(() => {
      this.stopOperation = null
    })
    return this.stopOperation
  }

  private async closeViewer({ logoff = !this.adopted }: { logoff?: boolean } = {}): Promise<void> {
    const orphanedSessionId = this.orphanedSessionId
    if (orphanedSessionId !== undefined) await this.ensureHost()
    if (!this.host) return
    const result = await this.exchange(
      { action: 'close', orphanedSessionId, logoff },
      event =>
        (event.event === 'state' && event.state === 'idle') ||
        (event.event === 'command_error' && event.action === 'close'),
      45000
    )
    if (result.event === 'command_error') {
      this.patch({ code: 'logoff_failed' })
      throw new DesktopSessionError('logoff_failed')
    }
    this.orphanedSessionId = undefined
    this.adopted = false
    await this.updateParentScope(null)
  }

  private async stopTasksAndCloseViewer(options?: { logoff?: boolean }): Promise<void> {
    if (this.disconnectPending || this.snapshot.executing) await this.stopTasks()
    await this.closeViewer(options)
  }

  async waitForStart(): Promise<void> {
    await this.startOperation
  }

  async getClosePrompt(manual: boolean): Promise<'close' | 'close-adopted' | undefined> {
    if (!this.active) return
    const { idle } = await this.pauseAdmissions(true)
    this.patch({ executing: !idle })
    if (this.adopted) return 'close-adopted'
    if (!manual || !idle) return 'close'
  }

  private async pauseAdmissions(closing: boolean): Promise<{ idle: boolean }> {
    if (closing) this.admissionsPaused = true
    const result = await request<{ idle: boolean }>(
      getLocalApiEndpoint(),
      internal + 'preview-closing',
      desktopSessionControlToken,
      { closing },
      5000
    )
    this.admissionsPaused = closing
    return result
  }

  async resumeAdmissions(): Promise<void> {
    if (this.admissionsPaused) await this.pauseAdmissions(false)
  }

  async close(options?: { logoff?: boolean }): Promise<void> {
    this.log('preview_close_started')
    this.patch({ closing: true })
    try {
      if (this.repairOperation) await this.repairOperation
      if (this.startOperation) await this.startOperation
      await this.startingHost?.catch(() => undefined)
      await this.stopTasksAndCloseViewer(options)
      await this.resumeAdmissions()
      this.log('viewer_closed')
      const child = this.host
      if (child) {
        this.send({ action: 'shutdown' })
        await once(child, 'exit', { signal: AbortSignal.timeout(10000) })
        this.log('host_shutdown_confirmed')
      }
      if (this.reserved) {
        await request(
          getLocalApiEndpoint(),
          internal + 'release',
          desktopSessionControlToken,
          undefined,
          5000
        )
        this.reserved = false
        this.log('preview_released')
      }
      this.volume = 0
      this.patch({ state: 'idle', windowState: 'visible' })
    } finally {
      this.patch({ closing: false })
      this.scheduleMonitor()
    }
  }

  position(bounds: [number, number, number, number]): void {
    if (this.host) this.send({ action: 'bounds', bounds })
  }

  changeWindow(state: DesktopSessionSnapshot['windowState']): void {
    if (this.host) this.send({ action: 'window', state })
  }

  changeVolume(volume: number): void {
    this.volume = volume
    if (this.host) this.send({ action: 'volume', volume })
  }
}
