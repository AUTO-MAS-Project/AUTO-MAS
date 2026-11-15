import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createInterface } from 'node:readline'
import { mkdirSync, appendFileSync, renameSync, statSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { getLocalApiEndpoint } from '../ipc/initializationHandlers'
import { beginMainFeature } from './featureAnalytics'
import { desktopSessionControlToken, setDesktopSessionChildId } from './desktopSessionControl'
import type {
  DesktopQueueResult,
  DesktopSessionRequest,
  DesktopSessionSnapshot,
  DesktopSessionStartResult,
} from './desktopSessionProtocol'

type HostEvent = Record<string, unknown> & { event: string }
type RuntimeDescription = { python: string; source: string; root: string }

class DesktopSessionError extends Error {}

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
  if (!response.ok) throw new DesktopSessionError(`http_${response.status}`)
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
  private runtime: RuntimeDescription | undefined
  private orphanedSessionId: number | undefined
  private hostEvents = new EventTarget()
  private startOperation: Promise<DesktopSessionStartResult> | null = null
  private stopOperation: Promise<void> | null = null
  private monitor: NodeJS.Timeout | undefined
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
    const runtime =
      this.runtime ??
      (await request<RuntimeDescription>(
        getLocalApiEndpoint(),
        internal + 'describe',
        desktopSessionControlToken,
        undefined,
        5000
      ))
    this.runtime = runtime
    this.logsRoot = join(runtime.root, 'debug', 'desktop-session')
    const child = spawn(runtime.python, ['-m', 'app.core.desktop_session.host', runtime.root], {
      cwd: runtime.source,
      windowsHide: true,
      stdio: 'pipe',
    })
    this.host = child
    const reader = createInterface({ input: child.stdout })
    reader.on('line', line => {
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
      this.patch({ state: this.active ? 'disconnected' : 'idle', code: 'host_exited' })
      this.scheduleMonitor()
    }
    child.once('error', exited)
    child.once('exit', exited)
    await this.wait(event => event.event === 'ready', 10000)
  }

  private handleHostEvent(event: HostEvent): void {
    if (typeof event.correlation === 'string') this.correlation = event.correlation
    if (event.event === 'diagnostics') {
      const checks = event.checks as DesktopSessionSnapshot['checks']
      this.patch({
        checks,
        ...(this.snapshot.state === 'checking'
          ? { state: checks.some(item => item.required && !item.ok) ? 'blocked' : 'idle' }
          : {}),
      })
    } else if (event.event === 'state') {
      const state = event.state as DesktopSessionSnapshot['state']
      this.patch({
        state: event.code === 'environment_blocked' ? 'blocked' : state,
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
      if (state === 'disconnected') this.scheduleMonitor()
    } else if (event.event === 'window') {
      this.patch({ windowState: event.state as DesktopSessionSnapshot['windowState'] })
    } else if (event.event === 'audio') {
      this.patch({ audioSessions: event.sessions as number })
    } else if (event.event === 'credential_warning') {
      this.patch({ code: 'credential_save_failed' })
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
    if (!this.active || this.snapshot.state === 'blocked') {
      this.patch({ state: 'checking', code: undefined })
    }
    try {
      await this.ensureHost()
      await this.exchange({ action: 'check' }, event => event.event === 'diagnostics', 20000)
    } catch (error) {
      this.patch({
        state: 'blocked',
        code: error instanceof DesktopSessionError ? error.message : 'host_unavailable',
      })
    }
    return this.snapshot
  }

  start(
    input: DesktopSessionRequest,
    owner: bigint,
    bounds: [number, number, number, number]
  ): Promise<DesktopSessionStartResult> {
    if (
      this.snapshot.busy ||
      this.snapshot.closing ||
      this.stopOperation ||
      this.orphanedSessionId !== undefined
    ) {
      return Promise.resolve({ code: 'busy', queues: [] })
    }
    this.patch({ busy: true, code: undefined })
    this.startOperation = this.startInternal(input, owner, bounds).finally(() => {
      this.startOperation = null
      this.patch({ busy: false })
      this.scheduleMonitor()
    })
    return this.startOperation
  }

  private async startInternal(
    input: DesktopSessionRequest,
    owner: bigint,
    bounds: [number, number, number, number]
  ): Promise<DesktopSessionStartResult> {
    const connection =
      this.snapshot.state !== 'connected'
        ? beginMainFeature('desktop_session_connection_finished')
        : null
    const dispatches = new Map<string, ReturnType<typeof beginMainFeature<'task_start_result'>>>()
    let publishingConnection = false
    try {
      await this.ensureHost()
      if (this.snapshot.state !== 'connected') {
        if (this.snapshot.state === 'disconnected') await this.closeViewer()
        publishingConnection = true
        await this.updateParentScope(null, true)
        const event = await this.exchange(
          {
            action: 'connect',
            resolution: input.resolution,
            mode: input.mode,
            password: input.password,
            owner: owner.toString(),
            bounds,
          },
          event =>
            (event.event === 'state' && event.state !== 'connecting') ||
            (event.event === 'command_error' && event.action === 'connect'),
          110000
        )
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
      if (!input.queueIds.length) return { queues: [] }
      for (const id of input.queueIds) {
        dispatches.set(id, beginMainFeature('task_start_result'))
      }
      if (this.snapshot.state !== 'connected') throw new DesktopSessionError('session_changed')
      this.patch({ executing: true })
      const result = await request<{ results: DesktopQueueResult[] }>(
        getLocalApiEndpoint(),
        internal + 'queues',
        desktopSessionControlToken,
        { queueIds: input.queueIds }
      )
      for (const queue of result.results) {
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
      const accepted = result.results.filter(target => target.taskId)
      if (accepted.length) this.tasksStarted(accepted)
      return { queues: result.results }
    } catch (error) {
      if (publishingConnection) {
        try {
          await this.closeViewer()
        } catch {
          this.log('process_scope_cleanup_failed')
        }
      }
      const code = error instanceof DesktopSessionError ? error.message : 'desktop_session_failed'
      const reason =
        code === 'environment_blocked'
          ? 'environment'
          : /password|credential|account/.test(code)
            ? 'credentials'
            : /rdp|connection|timeout/.test(code)
              ? 'connection'
              : 'process'
      connection?.finish({ outcome: 'failure', reason_kind: reason })
      this.patch({ code })
      this.log('start_failed', { code })
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

  private async updateParentScope(sessionId: number | null, connecting = false): Promise<void> {
    setDesktopSessionChildId(sessionId)
    if (!this.runtime) return
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
    if (this.snapshot.executing && !this.snapshot.closing) {
      this.monitor = setTimeout(() => void this.monitorExecution(), 1000)
    }
  }

  private async monitorExecution(): Promise<void> {
    if (this.startOperation || this.stopOperation || this.snapshot.closing) return
    const monitor = this.monitor
    try {
      if (this.snapshot.state === 'disconnected') {
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
        if (idle && this.monitor === monitor && !this.startOperation) {
          this.patch({ executing: false })
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
    this.stopOperation = request<{ idle: boolean }>(
      getLocalApiEndpoint(),
      internal + 'stop',
      desktopSessionControlToken
    )
      .then(({ idle }) => {
        if (!idle) throw new DesktopSessionError('executor_failed')
        this.patch({ executing: false })
      })
      .finally(() => {
        this.stopOperation = null
      })
    return this.stopOperation
  }

  private async closeViewer(): Promise<void> {
    const orphanedSessionId = this.orphanedSessionId
    if (orphanedSessionId !== undefined) await this.ensureHost()
    if (!this.host) return
    const result = await this.exchange(
      { action: 'close', orphanedSessionId },
      event =>
        (event.event === 'state' && event.state === 'idle') ||
        (event.event === 'command_error' && event.action === 'close'),
      45000
    )
    if (result.event === 'command_error') throw new DesktopSessionError('logoff_failed')
    this.orphanedSessionId = undefined
    await this.updateParentScope(null)
  }

  async close(): Promise<void> {
    this.patch({ closing: true })
    try {
      if (this.startOperation) await this.startOperation
      if (this.snapshot.executing) await this.stopTasks()
      await this.closeViewer()
      this.host?.stdin.end()
      this.host = null
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
