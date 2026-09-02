/**
 * Runtime NDJSON 输出的逐行解析器
 *
 * 只负责把子进程 stdout 的字节流切成行、把每行反序列化成协议事件。
 * 处理四件事：chunk 边界上的半行、空行、CRLF 换行、超长单行。
 * 单行解析失败或超限不会被吞掉，而是产生一条 `RUNTIME_PROTOCOL_ERROR` 条目交给调用方。
 */

import {
  RuntimeClientError,
  RuntimeErrorEvent,
  RuntimeEvent,
  RuntimeHelloEvent,
  RuntimeLogEvent,
  RuntimeProgressEvent,
  RuntimeResultEvent,
  RuntimeStateEvent,
  RuntimeWarningEvent,
} from './protocol'

/** 一次解析产出的条目。 */
export type NdjsonItem =
  | { kind: 'event'; event: RuntimeEvent; line: string }
  /** 行本身合法但 `type` 不在协议 v1 的事件全集内，按「忽略未知」处理。 */
  | { kind: 'unknown'; line: string }
  | { kind: 'error'; error: RuntimeClientError; line: string }

const EVENT_TYPES = new Set(['hello', 'progress', 'state', 'log', 'warning', 'error', 'result'])

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function asOptionalNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function asBoolean(value: unknown): boolean {
  return value === true
}

/** 容器字段协议上恒为对象/数组且不为 null，这里仍做一次防御性归一。 */
function asDetails(value: unknown): Record<string, unknown> {
  return asRecord(value) ?? {}
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

/**
 * 把一行 JSON 反序列化成协议事件。
 *
 * @throws {RuntimeClientError} `RUNTIME_PROTOCOL_ERROR`——行不是 JSON 对象，
 * 或缺少 `protocol`/`type` 这两个所有事件都必须携带的公共字段。
 */
export function parseRuntimeEventLine(line: string): RuntimeEvent | undefined {
  let decoded: unknown
  try {
    decoded = JSON.parse(line)
  } catch (error) {
    throw new RuntimeClientError(
      'RUNTIME_PROTOCOL_ERROR',
      `Runtime 输出了无法解析为 JSON 的行：${truncate(line)}`,
      { line },
      { cause: error }
    )
  }

  const raw = asRecord(decoded)
  if (!raw) {
    throw new RuntimeClientError(
      'RUNTIME_PROTOCOL_ERROR',
      `Runtime 输出的行不是 JSON 对象：${truncate(line)}`,
      { line }
    )
  }

  if (typeof raw.type !== 'string' || typeof raw.protocol !== 'number') {
    throw new RuntimeClientError(
      'RUNTIME_PROTOCOL_ERROR',
      `Runtime 事件缺少 protocol 或 type 字段：${truncate(line)}`,
      { line }
    )
  }

  if (!EVENT_TYPES.has(raw.type)) {
    return undefined
  }

  const common = {
    protocol: raw.protocol,
    operationId: asString(raw.operationId),
    sequence: asNumber(raw.sequence),
    timestamp: asString(raw.timestamp),
  }

  switch (raw.type) {
    case 'hello':
      return {
        ...common,
        type: 'hello',
        runtimeVersion: asString(raw.runtimeVersion),
        command: asString(raw.command),
        capabilities: asStringArray(raw.capabilities),
      } satisfies RuntimeHelloEvent

    case 'progress':
      return {
        ...common,
        type: 'progress',
        stage: asString(raw.stage),
        status: asString(raw.status),
        message: asString(raw.message),
        current: asOptionalNumber(raw.current),
        total: asOptionalNumber(raw.total),
        percent: asOptionalNumber(raw.percent),
      } satisfies RuntimeProgressEvent

    case 'state':
      return {
        ...common,
        type: 'state',
        stage: asString(raw.stage),
        status: asString(raw.status),
        message: asString(raw.message),
        details: asDetails(raw.details),
      } satisfies RuntimeStateEvent

    case 'log':
      return {
        ...common,
        type: 'log',
        source: asString(raw.source),
        stream: asString(raw.stream),
        message: asString(raw.message),
      } satisfies RuntimeLogEvent

    case 'warning':
      return {
        ...common,
        type: 'warning',
        code: asString(raw.code),
        stage: asString(raw.stage),
        message: asString(raw.message),
        retryable: asBoolean(raw.retryable),
        remediation: asStringArray(raw.remediation),
        details: asDetails(raw.details),
      } satisfies RuntimeWarningEvent

    case 'error':
      return {
        ...common,
        type: 'error',
        code: asString(raw.code),
        stage: asString(raw.stage),
        message: asString(raw.message),
        retryable: asBoolean(raw.retryable),
        remediation: asStringArray(raw.remediation),
        details: asDetails(raw.details),
      } satisfies RuntimeErrorEvent

    default:
      return {
        ...common,
        type: 'result',
        success: asBoolean(raw.success),
        code: asString(raw.code),
        stage: asString(raw.stage),
        status: asString(raw.status),
        message: asString(raw.message),
        retryable: asBoolean(raw.retryable),
        remediation: asStringArray(raw.remediation),
        details: asDetails(raw.details),
      } satisfies RuntimeResultEvent
  }
}

const MAX_ECHO_LENGTH = 200

function truncate(line: string): string {
  return line.length > MAX_ECHO_LENGTH ? `${line.slice(0, MAX_ECHO_LENGTH)}…` : line
}

/**
 * 单行的最大长度（UTF-16 码元数）。协议事件都是短行，超过这个长度只可能是
 * Runtime 输出通道坏了或对端根本不是 Runtime；不设上限的话半行会一直堆在内存里。
 */
export const MAX_NDJSON_LINE_LENGTH = 4 * 1024 * 1024

/**
 * NDJSON 增量解析器。
 *
 * 逐个 chunk 喂入，返回本次能确定的完整条目；进程退出后调用 `flush()`
 * 处理最后一行没有换行符的情况。
 *
 * 单行超过 `maxLineLength` 时按协议错误处理：丢弃该行已缓冲的内容，并继续丢弃
 * 直到下一个换行符为止，之后的行照常解析。
 */
export class NdjsonEventStream {
  private buffer = ''
  /** 当前行已超限，正在丢弃直到下一个换行符。 */
  private discarding = false
  /** 超限行被丢弃前的开头片段，用于报错时回显。 */
  private discardedHead = ''

  constructor(private readonly maxLineLength: number = MAX_NDJSON_LINE_LENGTH) {}

  /** 尚未凑齐换行符的半行内容，仅供诊断。 */
  get pending(): string {
    return this.buffer
  }

  push(chunk: string | Buffer): NdjsonItem[] {
    let text = typeof chunk === 'string' ? chunk : chunk.toString('utf8')
    const items: NdjsonItem[] = []

    if (this.discarding) {
      // 超限行的后续内容一个字符都不缓冲，直到看见换行符才恢复正常解析。
      const endOfLine = text.indexOf('\n')
      if (endOfLine === -1) {
        return items
      }
      items.push(this.finishDiscard())
      text = text.slice(endOfLine + 1)
    }

    this.buffer += text
    let newlineIndex = this.buffer.indexOf('\n')

    while (newlineIndex !== -1) {
      const line = this.buffer.slice(0, newlineIndex)
      this.buffer = this.buffer.slice(newlineIndex + 1)
      // 整行一次到齐但仍超限：同样按协议错误处理，不去解析它。
      const item =
        line.length > this.maxLineLength
          ? this.oversizedItem(line.slice(0, MAX_ECHO_LENGTH))
          : toItem(line)
      if (item) {
        items.push(item)
      }
      newlineIndex = this.buffer.indexOf('\n')
    }

    if (this.buffer.length > this.maxLineLength) {
      // 半行已经超限：记下开头片段后立刻释放缓冲，后续 chunk 直到换行符为止全部丢弃。
      if (!this.discarding) {
        this.discarding = true
        this.discardedHead = this.buffer.slice(0, MAX_ECHO_LENGTH)
      }
      this.buffer = ''
    }

    return items
  }

  /** 处理并清空残留缓冲。没有残留或残留全是空白时返回空数组。 */
  flush(): NdjsonItem[] {
    const rest = this.buffer
    this.buffer = ''
    const item = this.discarding ? this.finishDiscard() : toItem(rest)
    return item ? [item] : []
  }

  /** 超限行到达行尾（或流结束），产出一条协议错误并恢复正常解析。 */
  private finishDiscard(): NdjsonItem {
    const head = this.discardedHead
    this.discarding = false
    this.discardedHead = ''
    return this.oversizedItem(head)
  }

  private oversizedItem(head: string): NdjsonItem {
    return {
      kind: 'error',
      line: head,
      error: new RuntimeClientError(
        'RUNTIME_PROTOCOL_ERROR',
        `Runtime 输出了超过 ${this.maxLineLength} 个字符的单行，已丢弃：${head}…`,
        { line: head, maxLineLength: this.maxLineLength }
      ),
    }
  }
}

/** 把一行原始文本转成条目；空行（含 CRLF 造成的空行）直接跳过。 */
function toItem(rawLine: string): NdjsonItem | undefined {
  const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine
  if (line.trim().length === 0) {
    return undefined
  }

  try {
    const event = parseRuntimeEventLine(line)
    return event ? { kind: 'event', event, line } : { kind: 'unknown', line }
  } catch (error) {
    if (error instanceof RuntimeClientError) {
      return { kind: 'error', error, line }
    }
    throw error
  }
}
