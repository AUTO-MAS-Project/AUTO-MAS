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

describe('NdjsonEventStream', () => {
  it('半行超过长度上限时释放缓冲，行尾产出协议错误，后续行照常解析', () => {
    expect(parseRuntimeEventLine('{"protocol":1,"type":"future-event"}')).toBeUndefined()
    const [helloLine, progressLine, resultLine] = fixture('version.ndjson').trim().split('\n')
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
    const crlf = new NdjsonEventStream()
    expect(
      eventsOf(crlf.push(`${[helloLine, progressLine, resultLine].join('\r\n')}\r\n`)).map(
        event => event.type
      )
    ).toEqual(['hello', 'progress', 'result'])
    const malformed = new NdjsonEventStream()
    const malformedItems = malformed.push(`${helloLine}\n{"protocol":1,\n${progressLine}\n`)
    expect(malformedItems.map(item => item.kind)).toEqual(['event', 'error', 'event'])
    const bad = malformedItems[1]
    expect(bad.kind === 'error' && bad.error.code).toBe('RUNTIME_PROTOCOL_ERROR')
    expect(bad.line).toBe('{"protocol":1,')
    const shortLine = '{"protocol":1,"type":"progress","stage":"x","status":"succeeded"}'
    const oversized = new NdjsonEventStream(80)
    expect(oversized.push('x'.repeat(50))).toEqual([])
    expect(oversized.push('y'.repeat(50))).toEqual([])
    expect(oversized.pending).toBe('')
    expect(oversized.push('z'.repeat(50))).toEqual([])
    expect(oversized.pending).toBe('')
    const oversizedItems = oversized.push(`tail\n${shortLine}\n`)
    expect(oversizedItems.map(item => item.kind)).toEqual(['error', 'event'])
    const oversizedError = oversizedItems[0]
    if (oversizedError.kind !== 'error') throw new Error('第一条应为 error')
    expect(oversizedError.error.code).toBe('RUNTIME_PROTOCOL_ERROR')
    expect(oversizedError.error.message).toMatch(/超过 80 个字符/)
    expect(oversizedError.error.details.maxLineLength).toBe(80)
    expect(oversizedError.line).toBe('x'.repeat(50) + 'y'.repeat(50))
    expect(oversizedError.error.details.line).toBe(oversizedError.line)
    expect(eventsOf(oversizedItems)).toEqual([
      expect.objectContaining({ type: 'progress', stage: 'x', status: 'succeeded' }),
    ])
    expect(oversized.pending).toBe('')
    expect(oversized.flush()).toEqual([])
    const finalLine = new NdjsonEventStream()
    expect(finalLine.push(helloLine)).toEqual([])
    const flushed = finalLine.flush()
    expect(flushed).toHaveLength(1)
    expect(flushed[0].kind).toBe('event')
    expect(eventsOf(flushed)).toEqual([
      expect.objectContaining({
        type: 'hello',
        protocol: 1,
        command: 'version',
        operationId: JSON.parse(helloLine).operationId,
      }),
    ])
    expect(finalLine.pending).toBe('')
    expect(finalLine.flush()).toEqual([])
  })
})
