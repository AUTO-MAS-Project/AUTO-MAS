/**
 * AUTO-MAS Runtime 客户端
 *
 * 以「可执行文件路径 + 参数数组」spawn `auto-mas-runtime.exe`，固定使用
 * `--output ndjson --protocol 1` 机器调用模式，解析 NDJSON 事件流，并通过 stdin
 * 逐行下发控制命令。严禁拼接 shell 命令字符串。
 *
 * 两种调用形态：
 * - `run()`：一次性命令（version / doctor / bootstrap / workspace sync / … ），
 *   执行完退出，返回终态 `result`；
 * - `supervise()`：`backend supervise` 长驻形态，返回句柄，可发 status / cancel /
 *   shutdown，并等待最终 `result` 与进程退出。
 *
 * 本模块只做客户端封装，不负责替换现有初始化与后端服务。
 */

import { ChildProcessWithoutNullStreams, spawn } from 'child_process'
import { randomBytes } from 'crypto'
import { EventEmitter } from 'events'
import * as fs from 'fs'

import { getLogger } from '../logger'
import { NdjsonEventStream, NdjsonItem } from './ndjson'
import {
  RUNTIME_EXIT_CODES,
  RUNTIME_PROTOCOL_VERSION,
  RuntimeCapability,
  RuntimeClientError,
  RuntimeCode,
  RuntimeControlCommand,
  RuntimeControlKind,
  RuntimeErrorEvent,
  RuntimeEvent,
  RuntimeHelloEvent,
  RuntimeLogEvent,
  RuntimeProgressEvent,
  RuntimeResultEvent,
  RuntimeStateEvent,
  RuntimeWarningEvent,
  RuntimeWarningSummary,
} from './protocol'

const logger = getLogger('Runtime客户端')

/** 等待 hello 的默认超时。Runtime 参数解析后立刻发 hello，10 秒足够宽裕。 */
export const DEFAULT_HANDSHAKE_TIMEOUT_MS = 10_000

/** 收到 result 之后仍等待进程退出的宽限时间，超时则强制结束进程。 */
export const DEFAULT_RESULT_SETTLE_TIMEOUT_MS = 5_000

/** `shutdown()` 等待最终 result 与进程退出的默认超时，超时才 kill。 */
export const DEFAULT_SHUTDOWN_TIMEOUT_MS = 30_000

/** 判定失败并结束进程后，等待 close 事件的兜底时间，避免调用方永久挂起。 */
const FAIL_SETTLE_GRACE_MS = 2_000

/**
 * 保留的最近 log 事件条数。
 *
 * `backend supervise` 会把后端每一行 stdout / stderr（含 DEBUG 日志）都包装成 log 事件
 * 转发，整个监督期间无上限累积会把内存吃光；这里只留最近一段供失败展示与排查。
 */
export const DEFAULT_RECENT_LOG_CAPACITY = 500

// ==================== 选项与结果 ====================

/** 镜像源选择，对应 `--mirror <kind>=<key>`。 */
export interface RuntimeMirrorSelection {
  kind: 'git' | 'uv' | 'python' | 'package-index'
  key: string
}

export interface RuntimeClientOptions {
  /** `auto-mas-runtime.exe` 的绝对路径。 */
  runtimePath: string
  /** 传给 `--app-root` 的应用根目录。 */
  appRoot: string
  /**
   * 覆盖或追加到 `process.env` 的环境变量，例如 `AUTO_MAS_TELEMETRY=disabled`。
   * 值为 undefined 的键会被删除。
   */
  env?: NodeJS.ProcessEnv
  /** 全局镜像源选择，可重复。 */
  mirrors?: RuntimeMirrorSelection[]
  /** `--mirror-only`：只用配置的镜像源，排除官方源兜底。 */
  mirrorOnly?: boolean
  /** `--offline`：禁止任何网络尝试。与 mirror 选项互斥，冲突由 Runtime 判定。 */
  offline?: boolean
  /** 子进程工作目录，默认继承当前进程。 */
  cwd?: string
  handshakeTimeoutMs?: number
}

export interface RuntimeRunOptions {
  onEvent?: (event: RuntimeEvent) => void
  onProgress?: (event: RuntimeProgressEvent) => void
  onState?: (event: RuntimeStateEvent) => void
  onLog?: (event: RuntimeLogEvent) => void
  onWarning?: (event: RuntimeWarningEvent) => void
  /** Runtime 输出的 error 事件（不是调用侧错误）。 */
  onRuntimeError?: (event: RuntimeErrorEvent) => void
  /**
   * NDJSON 行解析失败。握手前的坏行会让本次调用直接失败；握手后的坏行只记录并回调，
   * 不会为一行脏输出杀掉在途命令或正在运行的后端。
   */
  onProtocolError?: (error: RuntimeClientError) => void
  handshakeTimeoutMs?: number
  /** 保留的最近 log 事件条数，默认 `DEFAULT_RECENT_LOG_CAPACITY`。 */
  recentLogCapacity?: number
}

/** 单个 operationId 下按流分组、保序的日志行。 */
export interface RuntimeLogBucket {
  stdout: string[]
  stderr: string[]
  /** stream 既不是 stdout 也不是 stderr 时的兜底分组。 */
  other: string[]
}

export type RuntimeLogsByOperation = Record<string, RuntimeLogBucket>

export interface RuntimeRunResult {
  hello: RuntimeHelloEvent
  result: RuntimeResultEvent
  /** `result.success`，避免调用方重复取值。 */
  success: boolean
  /** `result.code`，成功时为 `OK`。精确原因只能读它，不能读退出码。 */
  code: RuntimeCode
  /** 除 log 之外的全部事件；log 只保留最近一段，见 `recentLogs`。 */
  events: RuntimeEvent[]
  warnings: RuntimeWarningEvent[]
  errors: RuntimeErrorEvent[]
  /** 最近的 log 事件（最多 `recentLogCapacity` 条），保序。 */
  recentLogs: RuntimeLogEvent[]
  /** `recentLogs` 按 operationId 聚合后的结果。 */
  logs: RuntimeLogsByOperation
  /** 握手后被容忍的坏行。 */
  protocolErrors: RuntimeClientError[]
  exitCode: number | null
  signal: NodeJS.Signals | null
  /** Runtime 自身的 stderr 诊断输出。 */
  stderr: string
  /** 实际使用的参数数组，便于排查。 */
  argv: string[]
  durationMs: number
}

export interface RuntimeSuperviseOptions extends RuntimeRunOptions {
  /** `managed` 或 `development`；Runtime 要求显式指定，不提供默认值。 */
  mode: 'managed' | 'development'
  /** development 模式的源码目录。 */
  repo?: string
}

export interface RuntimeShutdownOptions {
  /** 等待最终 result 与进程退出的超时，超时才 kill。 */
  timeoutMs?: number
}

/** `backend supervise` 的长驻句柄。 */
export interface RuntimeSuperviseHandle {
  readonly hello: RuntimeHelloEvent
  readonly pid: number | undefined
  readonly capabilities: RuntimeCapability[]
  /** 最终 result 与进程退出后 resolve；未拿到 result 就退出则 reject。 */
  readonly completion: Promise<RuntimeRunResult>
  /** 订阅全部事件，返回取消订阅函数。 */
  onEvent(listener: (event: RuntimeEvent) => void): () => void
  /** 最近的 log 事件快照（最多 `recentLogCapacity` 条），返回副本。 */
  recentLogs(): RuntimeLogEvent[]
  /** 下发一条控制命令，返回本次生成的 commandId。 */
  sendControl(command: RuntimeControlKind): string
  /** 请求一次只读状态快照，返回 commandId。 */
  status(): string
  /** 请求取消，返回 commandId。 */
  cancel(): string
  /**
   * 发 shutdown 后等待最终 result 与进程退出，超时才 kill。
   *
   * hello 没宣告 `stdin.shutdown` 时不发命令、不等待，直接 kill 并以
   * `RUNTIME_EXITED_UNEXPECTEDLY` 收尾。
   */
  shutdown(options?: RuntimeShutdownOptions): Promise<RuntimeRunResult>
  /** 强制结束 Runtime 进程，只在兜底路径使用。 */
  kill(signal?: NodeJS.Signals): void
}

/** RuntimeClient 上的事件名。刻意不用 `error`，避免 EventEmitter 的抛异常语义。 */
export interface RuntimeClientEventMap {
  event: [RuntimeEvent]
  progress: [RuntimeProgressEvent]
  state: [RuntimeStateEvent]
  log: [RuntimeLogEvent]
  warning: [RuntimeWarningEvent]
  'runtime-error': [RuntimeErrorEvent]
  result: [RuntimeResultEvent]
  'protocol-error': [RuntimeClientError]
}

// ==================== 工具函数 ====================

const ULID_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
const ULID_TIMESTAMP_LENGTH = 10
const ULID_RANDOM_LENGTH = 16

/**
 * 生成规范 ULID 作为控制命令的 commandId。
 *
 * Runtime 用 `validOperationID` 校验 commandId：必须是 26 位 Crockford base32、
 * 首字符不大于 `7`。架构设计文档只写了「调用方生成的唯一 id」，实际不能用 UUID。
 */
export function createCommandId(now: number = Date.now()): string {
  let timestamp = ''
  let remaining = Math.max(0, Math.floor(now))
  for (let i = 0; i < ULID_TIMESTAMP_LENGTH; i += 1) {
    timestamp = ULID_ALPHABET[remaining % 32] + timestamp
    remaining = Math.floor(remaining / 32)
  }

  // 256 是 32 的整数倍，取模不引入偏置。
  const entropy = randomBytes(ULID_RANDOM_LENGTH)
  let random = ''
  for (let i = 0; i < ULID_RANDOM_LENGTH; i += 1) {
    random += ULID_ALPHABET[entropy[i] % 32]
  }

  return timestamp + random
}

/** 序列化一条 stdin 控制命令，末尾必须带换行符。 */
export function serializeControlCommand(command: RuntimeControlCommand): string {
  return `${JSON.stringify(command)}\n`
}

/** 拼装完整参数数组：全局选项在前，子命令在后。 */
export function buildRuntimeArgs(options: RuntimeClientOptions, command: string[]): string[] {
  const args = [
    '--app-root',
    options.appRoot,
    '--output',
    'ndjson',
    '--protocol',
    String(RUNTIME_PROTOCOL_VERSION),
  ]

  for (const mirror of options.mirrors ?? []) {
    args.push('--mirror', `${mirror.kind}=${mirror.key}`)
  }
  if (options.mirrorOnly) {
    args.push('--mirror-only')
  }
  if (options.offline) {
    args.push('--offline')
  }

  return [...args, ...command]
}

/**
 * 把启动阶段采集到的两路输出拼成一整块展示文本。
 *
 * 与 `backendService.ts` 的同名逻辑保持完全一致的展示格式，后续替换后端服务时沿用。
 */
export function formatStartupLogs(
  stdoutLines: readonly string[],
  stderrLines: readonly string[]
): string | undefined {
  const sections: string[] = []
  const stdout = stdoutLines.join('\n').trimEnd()
  const stderr = stderrLines.join('\n').trimEnd()

  if (stdout) {
    sections.push(`[stdout]\n${stdout}`)
  }

  if (stderr) {
    sections.push(`[stderr]\n${stderr}`)
  }

  return sections.length > 0 ? sections.join('\n\n') : undefined
}

/** 按 operationId 聚合 log 事件，stdout / stderr 分组且各自保序。 */
export function collectRuntimeLogs(events: readonly RuntimeEvent[]): RuntimeLogsByOperation {
  const logs: RuntimeLogsByOperation = {}
  for (const event of events) {
    if (event.type !== 'log') continue
    const bucket = (logs[event.operationId] ??= { stdout: [], stderr: [], other: [] })
    if (event.stream === 'stdout') {
      bucket.stdout.push(event.message)
    } else if (event.stream === 'stderr') {
      bucket.stderr.push(event.message)
    } else {
      bucket.other.push(event.message)
    }
  }
  return logs
}

/**
 * 从 `state` / `result` 事件的 details 中读取后端基地址。
 *
 * 契约 v1 固定为 `http://127.0.0.1:36163`，但调用方必须消费 Runtime 下发的值，
 * 不能自行假定 localhost 或端口。
 */
export function readRuntimeBaseUrl(details: Record<string, unknown>): string | undefined {
  const baseUrl = details.baseUrl
  return typeof baseUrl === 'string' && baseUrl.length > 0 ? baseUrl : undefined
}

/**
 * 从 `result.details.warnings` 读出 warning 快照（Go 侧 WarningSummary），字段不齐的条目跳过。
 *
 * Runtime 会把整个操作期间的 warning 汇总进最终 result；协议规定 result 之后不再有事件，
 * 所以这是调用方最后一次观察到「后端被强制终止」「遗留孤儿被回收」这类信息的机会。
 */
export function readRuntimeWarningSummaries(
  details: Record<string, unknown>
): RuntimeWarningSummary[] {
  const raw = details.warnings
  if (!Array.isArray(raw)) return []

  const summaries: RuntimeWarningSummary[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const candidate = item as Partial<RuntimeWarningSummary>
    if (typeof candidate.code !== 'string' || typeof candidate.message !== 'string') continue
    summaries.push({
      code: candidate.code,
      stage: typeof candidate.stage === 'string' ? candidate.stage : '',
      message: candidate.message,
      retryable: candidate.retryable === true,
      remediation: Array.isArray(candidate.remediation) ? candidate.remediation : [],
      details:
        candidate.details && typeof candidate.details === 'object'
          ? (candidate.details as Record<string, unknown>)
          : {},
    })
  }
  return summaries
}

/** 主进程日志里 details 的最大长度：孤儿清单最多 20 条，再长只会淹没日志。 */
const WARNING_DETAILS_LOG_LIMIT = 2000

function formatWarningDetails(details: Record<string, unknown>): string {
  let text: string
  try {
    text = JSON.stringify(details)
  } catch {
    text = String(details)
  }
  if (text === undefined || text === '{}') return ''
  if (text.length > WARNING_DETAILS_LOG_LIMIT) {
    text = `${text.slice(0, WARNING_DETAILS_LOG_LIMIT)}…（已截断）`
  }
  return `，details=${text}`
}

/**
 * warning 的日志级别。后端主进程被强杀（`BACKEND_FORCE_TERMINATED`）意味着正在跑的模拟器
 * 与任务状态被硬断，记 error；后端自己退出后遗留孙进程被 Job 回收（`BACKEND_ORPHANS_REAPED`）
 * 只是清理动作，与其他 warning 一样记 warn。
 */
function warningLogLevel(code: string): 'error' | 'warn' {
  return code === 'BACKEND_FORCE_TERMINATED' ? 'error' : 'warn'
}

/** warning 事件到达时写主进程日志：桌面侧此前完全看不到 Runtime 的 warning。 */
function logRuntimeWarning(event: RuntimeWarningEvent): void {
  const level = warningLogLevel(event.code)
  logger[level](
    `Runtime warning ${event.code}（阶段 ${event.stage}）：${event.message}${formatWarningDetails(event.details)}`
  )
}

/** result 携带的 warning 汇总：每条 warning 已在事件到达时带 details 记过，这里只列结论。 */
function logRuntimeResultWarnings(event: RuntimeResultEvent): void {
  const summaries = readRuntimeWarningSummaries(event.details)
  if (summaries.length === 0) return

  const codes = summaries.map(summary => summary.code)
  const level = codes.some(code => warningLogLevel(code) === 'error') ? 'error' : 'warn'
  const truncated = event.details.warningsTruncated === true ? '，且已截断' : ''
  logger[level](
    `Runtime 终态 ${event.code}（${event.stage}/${event.status}）携带 ${summaries.length} 条 warning：${codes.join(', ')}${truncated}`
  )
}

function mergeEnv(overrides?: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env }
  for (const [key, value] of Object.entries(overrides ?? {})) {
    if (value === undefined) {
      delete env[key]
      continue
    }
    env[key] = value
  }
  return env
}

/** 固定容量的环形缓冲，满了之后覆盖最旧的一条。 */
class RingBuffer<T> {
  private readonly slots: T[]
  private next = 0
  private count = 0

  constructor(capacity: number) {
    this.slots = new Array<T>(Math.max(1, Math.floor(capacity)))
  }

  push(item: T): void {
    this.slots[this.next] = item
    this.next = (this.next + 1) % this.slots.length
    this.count = Math.min(this.count + 1, this.slots.length)
  }

  /** 按写入顺序导出副本。 */
  toArray(): T[] {
    if (this.count < this.slots.length) {
      return this.slots.slice(0, this.count)
    }
    return [...this.slots.slice(this.next), ...this.slots.slice(0, this.next)]
  }
}

// ==================== 会话 ====================

/** 一次 Runtime 调用的内部状态机，run 与 supervise 共用。 */
class RuntimeSession {
  readonly argv: string[]
  readonly child: ChildProcessWithoutNullStreams
  readonly hello: Promise<RuntimeHelloEvent>
  readonly completion: Promise<RuntimeRunResult>

  private readonly listeners = new Set<(event: RuntimeEvent) => void>()
  private readonly stdoutStream = new NdjsonEventStream()
  /** 除 log 之外的事件。log 只进 `recentLogs`，否则长驻监督会无上限堆内存。 */
  private readonly events: RuntimeEvent[] = []
  private readonly recentLogs: RingBuffer<RuntimeLogEvent>
  private readonly warnings: RuntimeWarningEvent[] = []
  private readonly errors: RuntimeErrorEvent[] = []
  private readonly protocolErrors: RuntimeClientError[] = []
  private readonly stderrChunks: string[] = []
  private readonly startedAt = Date.now()

  private helloEvent: RuntimeHelloEvent | undefined
  private resultEvent: RuntimeResultEvent | undefined
  private failure: RuntimeClientError | undefined
  private settled = false
  private handshakeTimer: NodeJS.Timeout | undefined
  private resultSettleTimer: NodeJS.Timeout | undefined
  private failSettleTimer: NodeJS.Timeout | undefined

  private resolveHello!: (value: RuntimeHelloEvent) => void
  private rejectHello!: (reason: unknown) => void
  private resolveCompletion!: (value: RuntimeRunResult) => void
  private rejectCompletion!: (reason: unknown) => void

  constructor(
    private readonly clientOptions: RuntimeClientOptions,
    command: string[],
    private readonly options: RuntimeRunOptions,
    private readonly emitter: EventEmitter
  ) {
    this.argv = buildRuntimeArgs(clientOptions, command)
    this.recentLogs = new RingBuffer(options.recentLogCapacity ?? DEFAULT_RECENT_LOG_CAPACITY)

    this.hello = new Promise<RuntimeHelloEvent>((resolve, reject) => {
      this.resolveHello = resolve
      this.rejectHello = reject
    })
    this.completion = new Promise<RuntimeRunResult>((resolve, reject) => {
      this.resolveCompletion = resolve
      this.rejectCompletion = reject
    })
    // hello 与 completion 会同时失败，而 run() 只 await 其中一个；
    // 这里各挂一个空 catch 标记为已处理，避免 unhandled rejection 警告。
    this.hello.catch(() => undefined)
    this.completion.catch(() => undefined)

    if (!fs.existsSync(clientOptions.runtimePath)) {
      throw new RuntimeClientError(
        'RUNTIME_NOT_FOUND',
        `找不到 Runtime 可执行文件：${clientOptions.runtimePath}`,
        { runtimePath: clientOptions.runtimePath, argv: this.argv }
      )
    }

    logger.debug(`启动 Runtime：${clientOptions.runtimePath} ${this.argv.join(' ')}`)

    // detached：让 Runtime 脱离 libuv 给非 detached 子进程套的 KILL_ON_JOB_CLOSE Job。
    // 否则宿主被强杀时 Runtime 会随 Job 一起消失，拿不到 stdin EOF，后端没有优雅清理的机会。
    // 三路 stdio 仍是管道：NDJSON 事件与 stdin 控制都靠它们；宿主退出（正常或被强杀）时
    // 管道随之关闭，Runtime 按契约把 stdin EOF 视为隐式 shutdown，优雅关闭后端后自行退出，
    // 不会留下永久孤儿。不 unref：close 事件与兜底 kill 仍由本会话负责。
    this.child = spawn(clientOptions.runtimePath, this.argv, {
      cwd: clientOptions.cwd,
      env: mergeEnv(clientOptions.env),
      windowsHide: true,
      detached: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    }) as ChildProcessWithoutNullStreams

    this.child.stdout?.setEncoding('utf8')
    this.child.stderr?.setEncoding('utf8')
    this.child.stdout?.on('data', chunk => this.consumeStdout(chunk))
    this.child.stderr?.on('data', chunk => this.stderrChunks.push(String(chunk)))
    this.child.stdin?.on('error', error => {
      logger.warn(`向 Runtime stdin 写入失败：${String(error)}`)
    })
    this.child.on('error', error => this.onSpawnError(error))
    this.child.on('close', (code, signal) => this.onClose(code, signal))

    const timeoutMs =
      options.handshakeTimeoutMs ?? clientOptions.handshakeTimeoutMs ?? DEFAULT_HANDSHAKE_TIMEOUT_MS
    this.handshakeTimer = setTimeout(() => {
      this.fail(
        new RuntimeClientError(
          'RUNTIME_HANDSHAKE_TIMEOUT',
          `等待 Runtime hello 事件超过 ${timeoutMs}ms`,
          { runtimePath: clientOptions.runtimePath, argv: this.argv, stderr: this.stderr() }
        )
      )
    }, timeoutMs)
    this.handshakeTimer.unref?.()
  }

  addListener(listener: (event: RuntimeEvent) => void): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  sendControl(command: RuntimeControlKind): string {
    const commandId = createCommandId()
    const payload: RuntimeControlCommand = {
      protocol: RUNTIME_PROTOCOL_VERSION,
      command,
      commandId,
    }

    const stdin = this.child.stdin
    if (!stdin || stdin.destroyed || stdin.writableEnded) {
      logger.warn(`Runtime stdin 已关闭，控制命令 ${command} 未能下发`)
      return commandId
    }

    stdin.write(serializeControlCommand(payload))
    logger.debug(`已下发控制命令 ${command}，commandId=${commandId}`)
    return commandId
  }

  kill(signal?: NodeJS.Signals): void {
    if (this.child.exitCode === null && !this.child.killed) {
      this.child.kill(signal)
    }
  }

  private stderr(): string {
    return this.stderrChunks.join('')
  }

  private consumeStdout(chunk: string | Buffer): void {
    for (const item of this.stdoutStream.push(chunk)) {
      this.consumeItem(item)
    }
  }

  private consumeItem(item: NdjsonItem): void {
    if (item.kind === 'unknown') {
      logger.debug(`忽略未知类型的 Runtime 事件：${item.line}`)
      return
    }

    if (item.kind === 'error') {
      this.onProtocolError(item.error)
      return
    }

    this.dispatch(item.event)
  }

  private onProtocolError(error: RuntimeClientError): void {
    this.protocolErrors.push(error)
    logger.error(`Runtime NDJSON 解析失败：${error.message}`)
    this.options.onProtocolError?.(error)
    this.emitter.emit('protocol-error', error)

    // 握手前的坏行说明对端根本不是按协议说话的 Runtime，直接失败；
    // 握手后的坏行只记录并回调，不为一行脏输出杀掉在途命令或正在运行的后端。
    if (!this.helloEvent) {
      this.fail(error)
    }
  }

  /** 最近 log 事件的副本，按到达顺序。 */
  recentLogSnapshot(): RuntimeLogEvent[] {
    return this.recentLogs.toArray()
  }

  private dispatch(event: RuntimeEvent): void {
    if (event.type === 'log') {
      this.recentLogs.push(event)
    } else {
      this.events.push(event)
    }

    switch (event.type) {
      case 'hello':
        this.onHello(event)
        break
      case 'progress':
        this.options.onProgress?.(event)
        this.emitter.emit('progress', event)
        break
      case 'state':
        this.options.onState?.(event)
        this.emitter.emit('state', event)
        break
      case 'log':
        this.options.onLog?.(event)
        this.emitter.emit('log', event)
        break
      case 'warning':
        this.warnings.push(event)
        logRuntimeWarning(event)
        this.options.onWarning?.(event)
        this.emitter.emit('warning', event)
        break
      case 'error':
        this.errors.push(event)
        this.options.onRuntimeError?.(event)
        this.emitter.emit('runtime-error', event)
        break
      case 'result':
        this.onResult(event)
        break
    }

    this.options.onEvent?.(event)
    this.emitter.emit('event', event)
    for (const listener of this.listeners) {
      listener(event)
    }
  }

  private onHello(event: RuntimeHelloEvent): void {
    if (this.handshakeTimer) {
      clearTimeout(this.handshakeTimer)
      this.handshakeTimer = undefined
    }

    if (event.protocol !== RUNTIME_PROTOCOL_VERSION) {
      this.fail(
        new RuntimeClientError(
          'RUNTIME_PROTOCOL_MISMATCH',
          `Runtime 握手协议版本为 ${event.protocol}，本程序要求 ${RUNTIME_PROTOCOL_VERSION}`,
          {
            actualProtocol: event.protocol,
            expectedProtocol: RUNTIME_PROTOCOL_VERSION,
            runtimePath: this.clientOptions.runtimePath,
            argv: this.argv,
          }
        )
      )
      return
    }

    this.helloEvent = event
    logger.info(
      `Runtime ${event.runtimeVersion} 已握手，命令 ${event.command}，能力 [${event.capabilities.join(', ')}]`
    )
    this.resolveHello(event)
  }

  private onResult(event: RuntimeResultEvent): void {
    this.resultEvent = event
    logRuntimeResultWarnings(event)
    this.emitter.emit('result', event)
    // 协议规定 result 之后不再有任何事件，进程应随即退出；给一段宽限再兜底 kill。
    this.resultSettleTimer = setTimeout(() => {
      logger.warn('Runtime 输出 result 后未按期退出，强制结束进程')
      this.kill()
    }, DEFAULT_RESULT_SETTLE_TIMEOUT_MS)
    this.resultSettleTimer.unref?.()
  }

  private onSpawnError(error: NodeJS.ErrnoException): void {
    const code = error.code === 'ENOENT' ? 'RUNTIME_NOT_FOUND' : 'RUNTIME_SPAWN_FAILED'
    this.fail(
      new RuntimeClientError(
        code,
        `启动 Runtime 失败：${error.message}`,
        { runtimePath: this.clientOptions.runtimePath, argv: this.argv, stderr: this.stderr() },
        { cause: error }
      )
    )
  }

  private onClose(exitCode: number | null, signal: NodeJS.Signals | null): void {
    for (const item of this.stdoutStream.flush()) {
      this.consumeItem(item)
    }

    if (this.handshakeTimer) {
      clearTimeout(this.handshakeTimer)
      this.handshakeTimer = undefined
    }
    if (this.resultSettleTimer) {
      clearTimeout(this.resultSettleTimer)
      this.resultSettleTimer = undefined
    }
    if (this.failSettleTimer) {
      clearTimeout(this.failSettleTimer)
      this.failSettleTimer = undefined
    }

    if (this.settled) return

    if (this.failure) {
      this.settle(this.failure, exitCode, signal)
      return
    }

    if (this.helloEvent && this.resultEvent) {
      this.settled = true
      this.resolveCompletion(this.buildResult(this.helloEvent, this.resultEvent, exitCode, signal))
      return
    }

    // 参数解析失败或协议不匹配时 Runtime 不承诺 hello/result，只有 stderr 与退出码。
    // 实测 `--protocol 2` 就是 stdout 全空、stderr 一行诊断、退出码 10。
    const mismatched = !this.helloEvent && exitCode === RUNTIME_EXIT_CODES.protocolMismatch
    const error = mismatched
      ? new RuntimeClientError(
          'RUNTIME_PROTOCOL_MISMATCH',
          `Runtime 以协议不兼容退出（退出码 ${exitCode}）`,
          {
            exitCode,
            signal,
            stderr: this.stderr(),
            expectedProtocol: RUNTIME_PROTOCOL_VERSION,
            runtimePath: this.clientOptions.runtimePath,
            argv: this.argv,
          }
        )
      : new RuntimeClientError(
          'RUNTIME_EXITED_UNEXPECTEDLY',
          `Runtime 未输出最终 result 就退出（退出码 ${exitCode}${signal ? `，信号 ${signal}` : ''}）`,
          {
            exitCode,
            signal,
            stderr: this.stderr(),
            runtimePath: this.clientOptions.runtimePath,
            argv: this.argv,
          }
        )

    this.settle(error, exitCode, signal)
  }

  /** 记录致命错误并结束进程；真正 reject 发生在进程 close 时，以便带上退出码。 */
  private fail(error: RuntimeClientError): void {
    if (this.settled || this.failure) return
    this.failure = error
    if (this.handshakeTimer) {
      clearTimeout(this.handshakeTimer)
      this.handshakeTimer = undefined
    }
    this.rejectHello(error)
    this.kill()
    if (this.settled) return

    // 进程若不响应结束信号，close 可能迟迟不来；兜底收敛避免调用方永久挂起。
    this.failSettleTimer = setTimeout(() => {
      this.settle(error, this.child.exitCode, this.child.signalCode)
    }, FAIL_SETTLE_GRACE_MS)
    this.failSettleTimer.unref?.()
  }

  private settle(
    error: RuntimeClientError,
    exitCode: number | null,
    signal: NodeJS.Signals | null
  ) {
    if (this.settled) return
    this.settled = true
    if (error.details.exitCode === undefined) {
      error.details.exitCode = exitCode
      error.details.signal = signal
      error.details.stderr = error.details.stderr || this.stderr()
    }
    this.rejectHello(error)
    this.rejectCompletion(error)
  }

  private buildResult(
    hello: RuntimeHelloEvent,
    result: RuntimeResultEvent,
    exitCode: number | null,
    signal: NodeJS.Signals | null
  ): RuntimeRunResult {
    const recentLogs = this.recentLogs.toArray()
    return {
      hello,
      result,
      success: result.success,
      code: result.code,
      events: this.events,
      warnings: this.warnings,
      errors: this.errors,
      recentLogs,
      logs: collectRuntimeLogs(recentLogs),
      protocolErrors: this.protocolErrors,
      exitCode,
      signal,
      stderr: this.stderr(),
      argv: this.argv,
      durationMs: Date.now() - this.startedAt,
    }
  }
}

// ==================== 客户端 ====================

/**
 * Runtime 客户端。
 *
 * 除了每次调用可传的回调，实例本身也是 EventEmitter，转发 `event`、`progress`、
 * `state`、`log`、`warning`、`runtime-error`、`result` 与 `protocol-error`。
 * 刻意不使用 `error` 事件名，避免无监听者时 EventEmitter 直接抛出。
 */
export class RuntimeClient extends EventEmitter {
  constructor(private readonly options: RuntimeClientOptions) {
    super()
  }

  get runtimePath(): string {
    return this.options.runtimePath
  }

  get appRoot(): string {
    return this.options.appRoot
  }

  /**
   * 执行一次性命令并等待终态 `result`。
   *
   * @param command 子命令与其参数，例如 `['workspace', 'sync', '--version', 'v5.5.0']`。
   * @throws {RuntimeClientError} 见 `RuntimeClientErrorCode`。Runtime 自己报告的失败
   * 不会抛异常，而是以 `result.success === false` 返回，由调用方读 `result.code`。
   */
  async run(command: string[], options: RuntimeRunOptions = {}): Promise<RuntimeRunResult> {
    const session = new RuntimeSession(this.options, command, options, this)

    await session.hello
    return session.completion
  }

  /**
   * 启动 `backend supervise` 长驻形态，握手成功后返回句柄。
   *
   * 句柄的 `completion` 在最终 `result` 与进程退出后 resolve。握手之后出现的坏行
   * 不会中断被监督的后端，只记录并回调，避免为一行脏输出杀掉正在运行的后端。
   */
  async supervise(options: RuntimeSuperviseOptions): Promise<RuntimeSuperviseHandle> {
    const command = ['backend', 'supervise', '--mode', options.mode]
    if (options.repo) {
      command.push('--repo', options.repo)
    }

    const session = new RuntimeSession(this.options, command, options, this)

    const hello = await session.hello
    const canShutdown = hello.capabilities.includes('stdin.shutdown')
    let shutdownRequested = false

    return {
      hello,
      pid: session.child.pid,
      capabilities: hello.capabilities,
      completion: session.completion,
      onEvent: listener => session.addListener(listener),
      recentLogs: () => session.recentLogSnapshot(),
      sendControl: command => session.sendControl(command),
      status: () => session.sendControl('status'),
      cancel: () => session.sendControl('cancel'),
      kill: signal => session.kill(signal),
      shutdown: async ({ timeoutMs = DEFAULT_SHUTDOWN_TIMEOUT_MS } = {}) => {
        if (!canShutdown) {
          // 调用方按契约只信 hello 宣告的能力：没宣告 stdin.shutdown 就不发命令，
          // 也不白等超时，直接走强制结束这条退路。
          logger.warn(
            `Runtime 未宣告 stdin.shutdown 能力（已宣告 [${hello.capabilities.join(', ')}]），跳过优雅关闭，直接强制结束进程`
          )
          session.kill()
          return session.completion
        }

        if (!shutdownRequested) {
          shutdownRequested = true
          session.sendControl('shutdown')
        }

        const timer = setTimeout(() => {
          logger.warn(`Runtime 在 ${timeoutMs}ms 内未完成关闭，强制结束进程`)
          session.kill()
        }, timeoutMs)
        timer.unref?.()

        try {
          return await session.completion
        } finally {
          clearTimeout(timer)
        }
      },
    }
  }
}
