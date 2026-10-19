import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vite-plus/test'

import { NdjsonEventStream, parseRuntimeEventLine } from './ndjson'

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

  it('合法 JSON 但不是对象或缺少公共字段同样报协议错误', () => {
    expect(() => parseRuntimeEventLine('[1,2,3]')).toThrowError(/不是 JSON 对象/)
    expect(() => parseRuntimeEventLine('"hello"')).toThrowError(/不是 JSON 对象/)
    expect(() => parseRuntimeEventLine('{"type":"hello"}')).toThrowError(/缺少 protocol 或 type/)
    expect(() => parseRuntimeEventLine('{"protocol":1}')).toThrowError(/缺少 protocol 或 type/)
  })

  it('未知事件类型返回 undefined 而不是拒绝整条协议', () => {
    expect(parseRuntimeEventLine('{"protocol":1,"type":"future-event"}')).toBeUndefined()
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
