import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { MAX_NDJSON_LINE_LENGTH, NdjsonEventStream, parseRuntimeEventLine } from './ndjson'
import { RuntimeClientError } from './protocol'

const fixturesDir = join(dirname(fileURLToPath(import.meta.url)), '__fixtures__')

/** 夹具由本机构建的 auto-mas-runtime.exe 真实跑出来，不是手写的。 */
function fixture(name: string): string {
  return readFileSync(join(fixturesDir, name), 'utf8')
}

function eventsOf(items: ReturnType<NdjsonEventStream['push']>) {
  return items.flatMap(item => (item.kind === 'event' ? [item.event] : []))
}

describe('parseRuntimeEventLine', () => {
  it('解析真实 version 输出的三条事件', () => {
    const lines = fixture('version.ndjson').trim().split('\n')
    const events = lines.map(line => parseRuntimeEventLine(line))

    expect(events).toHaveLength(3)
    const [hello, progress, result] = events

    expect(hello).toMatchObject({
      type: 'hello',
      protocol: 1,
      sequence: 1,
      command: 'version',
      runtimeVersion: 'dev',
      capabilities: [],
    })
    expect(progress).toMatchObject({
      type: 'progress',
      stage: 'runtime.handshake',
      status: 'succeeded',
    })
    expect(result).toMatchObject({
      type: 'result',
      success: true,
      code: 'OK',
      stage: 'runtime.handshake',
      status: 'succeeded',
      remediation: [],
    })
    expect(result?.type === 'result' && result.details.protocolVersion).toBe(1)
  })

  it('解析真实 doctor 输出并保留 details 结构', () => {
    const lines = fixture('doctor.ndjson').trim().split('\n')
    const events = lines.map(line => parseRuntimeEventLine(line))

    expect(events).toHaveLength(21)
    expect(events.filter(event => event?.type === 'progress')).toHaveLength(19)

    const result = events.at(-1)
    expect(result?.type).toBe('result')
    if (result?.type !== 'result') throw new Error('最后一条应为 result')
    expect(result.success).toBe(true)
    expect(result.details.summary).toMatchObject({ total: 9, ok: 3, missing: 6, error: 0 })
  })

  it('解析 supervise 的 hello 能力与失败 result', () => {
    const lines = fixture('supervise-invalid-mode.ndjson').trim().split('\n')
    const [hello, error, result] = lines.map(line => parseRuntimeEventLine(line))

    expect(hello?.type === 'hello' && hello.capabilities).toEqual([
      'stdin.cancel',
      'state.v1',
      'log.stream',
    ])
    expect(error).toMatchObject({
      type: 'error',
      code: 'INVALID_ARGUMENT',
      stage: 'backend.spawn',
      retryable: false,
      remediation: ['run-doctor'],
      details: { field: 'mode' },
    })
    // 失败 result 复述主错误的稳定四元组，调用方只消费终点事件即可。
    // status 这里是进度语义的 failed，而不是生命周期状态：Runtime 还没进入后端生命周期
    // 就因参数错误结束了。同一命令走到 managed 分支失败时该字段会是 backend_failed。
    expect(result).toMatchObject({
      type: 'result',
      success: false,
      code: 'INVALID_ARGUMENT',
      status: 'failed',
      retryable: false,
      remediation: ['run-doctor'],
    })
  })

  it('解析取消场景里的 warning 与 result 汇总', () => {
    const lines = fixture('cancelled-with-warning.ndjson').trim().split('\n')
    const events = lines.map(line => parseRuntimeEventLine(line))
    const warning = events.find(event => event?.type === 'warning')
    const result = events.at(-1)

    expect(warning).toMatchObject({
      code: 'INVALID_CONTROL_COMMAND',
      retryable: false,
      remediation: ['update-desktop'],
      details: { reason: 'invalid_json' },
    })
    if (result?.type !== 'result') throw new Error('最后一条应为 result')
    expect(result.code).toBe('OPERATION_CANCELLED')
    expect(result.status).toBe('cancelled')
    expect(result.details.warningCount).toBe(1)
    expect(result.details.controlCommandId).toEqual(expect.any(String))
  })

  it('坏 JSON 行抛出 RUNTIME_PROTOCOL_ERROR 并带上原始行', () => {
    expect(() => parseRuntimeEventLine('{"protocol":1,')).toThrowError(RuntimeClientError)

    try {
      parseRuntimeEventLine('not json at all')
      throw new Error('应当抛出')
    } catch (error) {
      expect(error).toBeInstanceOf(RuntimeClientError)
      const clientError = error as RuntimeClientError
      expect(clientError.code).toBe('RUNTIME_PROTOCOL_ERROR')
      expect(clientError.retryable).toBe(false)
      expect(clientError.details.line).toBe('not json at all')
    }
  })

  it('合法 JSON 但不是对象或缺少公共字段同样报协议错误', () => {
    expect(() => parseRuntimeEventLine('[1,2,3]')).toThrowError(/不是 JSON 对象/)
    expect(() => parseRuntimeEventLine('"hello"')).toThrowError(/不是 JSON 对象/)
    expect(() => parseRuntimeEventLine('{"type":"hello"}')).toThrowError(/缺少 protocol 或 type/)
    expect(() => parseRuntimeEventLine('{"protocol":1}')).toThrowError(/缺少 protocol 或 type/)
  })

  it('未知事件类型返回 undefined 而不是拒绝整条协议', () => {
    expect(parseRuntimeEventLine('{"protocol":1,"type":"future-event"}')).toBeUndefined()
  })

  it('容器字段缺失时归一为空对象/空数组', () => {
    const event = parseRuntimeEventLine(
      '{"protocol":1,"type":"error","code":"INTERNAL_ERROR","stage":"doctor","message":"x"}'
    )

    expect(event).toMatchObject({ remediation: [], details: {}, retryable: false })
  })
})

describe('NdjsonEventStream', () => {
  it('跨 chunk 拼接半行', () => {
    const [helloLine, progressLine] = fixture('version.ndjson').trim().split('\n')
    const stream = new NdjsonEventStream()

    const half = helloLine.slice(0, 40)
    expect(stream.push(half)).toEqual([])
    expect(stream.pending).toBe(half)

    const items = stream.push(`${helloLine.slice(40)}\n${progressLine}\n`)
    const events = eventsOf(items)

    expect(events).toHaveLength(2)
    expect(events[0].type).toBe('hello')
    expect(events[1].type).toBe('progress')
    expect(stream.pending).toBe('')
  })

  it('一次 chunk 内的多行与 CRLF 都能切开', () => {
    const lines = fixture('version.ndjson').trim().split('\n')
    const stream = new NdjsonEventStream()

    const events = eventsOf(stream.push(`${lines.join('\r\n')}\r\n`))

    expect(events.map(event => event.type)).toEqual(['hello', 'progress', 'result'])
  })

  it('空行与纯空白行被跳过', () => {
    const [helloLine] = fixture('version.ndjson').trim().split('\n')
    const stream = new NdjsonEventStream()

    const items = stream.push(`\n\r\n   \n${helloLine}\n\n`)

    expect(items).toHaveLength(1)
    expect(items[0].kind).toBe('event')
  })

  it('坏行产生 error 条目但不影响后续行', () => {
    const [helloLine, progressLine] = fixture('version.ndjson').trim().split('\n')
    const stream = new NdjsonEventStream()

    const items = stream.push(`${helloLine}\n{"protocol":1,\n${progressLine}\n`)

    expect(items.map(item => item.kind)).toEqual(['event', 'error', 'event'])
    const bad = items[1]
    expect(bad.kind === 'error' && bad.error.code).toBe('RUNTIME_PROTOCOL_ERROR')
    expect(bad.line).toBe('{"protocol":1,')
  })

  // 一条比 80 字符上限短的合法事件行，用来验证超限行之后能恢复正常解析。
  const shortLine = '{"protocol":1,"type":"progress","stage":"x","status":"succeeded"}'

  it('半行超过长度上限时释放缓冲，行尾产出协议错误，后续行照常解析', () => {
    const stream = new NdjsonEventStream(80)

    // 三个 chunk 拼出一条 150 字符的半行，超限后缓冲不再增长。
    expect(stream.push('x'.repeat(50))).toEqual([])
    expect(stream.push('y'.repeat(50))).toEqual([])
    expect(stream.pending).toBe('')
    expect(stream.push('z'.repeat(50))).toEqual([])
    expect(stream.pending).toBe('')

    const items = stream.push(`tail\n${shortLine}\n`)

    expect(items.map(item => item.kind)).toEqual(['error', 'event'])
    const bad = items[0]
    if (bad.kind !== 'error') throw new Error('第一条应为 error')
    expect(bad.error.code).toBe('RUNTIME_PROTOCOL_ERROR')
    expect(bad.error.message).toMatch(/超过 80 个字符/)
    expect(bad.error.details.maxLineLength).toBe(80)
    // 回显只保留开头片段，不把超长内容原样带出去。
    expect(bad.line).toBe('x'.repeat(50) + 'y'.repeat(50))
    expect(bad.error.details.line).toBe(bad.line)
    expect(stream.pending).toBe('')
  })

  it('一次到齐的整行超限同样按协议错误丢弃', () => {
    const stream = new NdjsonEventStream(80)

    const items = stream.push(`${'{'.repeat(100)}\n${shortLine}\n`)

    expect(items.map(item => item.kind)).toEqual(['error', 'event'])
    expect(items[0].kind === 'error' && items[0].error.code).toBe('RUNTIME_PROTOCOL_ERROR')
  })

  it('流在超限半行中结束时 flush 仍产出协议错误', () => {
    const stream = new NdjsonEventStream(80)

    stream.push('x'.repeat(100))
    const flushed = stream.flush()

    expect(flushed).toHaveLength(1)
    expect(flushed[0].kind === 'error' && flushed[0].error.code).toBe('RUNTIME_PROTOCOL_ERROR')
    expect(stream.flush()).toEqual([])
  })

  it('默认上限为 4 MiB', () => {
    expect(MAX_NDJSON_LINE_LENGTH).toBe(4 * 1024 * 1024)
  })

  it('flush 处理结尾没有换行符的最后一行', () => {
    const [helloLine] = fixture('version.ndjson').trim().split('\n')
    const stream = new NdjsonEventStream()

    expect(stream.push(helloLine)).toEqual([])
    const flushed = stream.flush()

    expect(flushed).toHaveLength(1)
    expect(flushed[0].kind).toBe('event')
    expect(stream.flush()).toEqual([])
  })
})
