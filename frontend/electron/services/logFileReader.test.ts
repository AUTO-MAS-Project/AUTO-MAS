import { mkdtempSync, rmSync, writeFileSync, appendFileSync, unlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { incompleteUtf8TailLength, readLogContent, readLogIncrement } from './logFileReader'

let dir: string
let logPath: string

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'mas-log-reader-'))
  logPath = join(dir, 'app.log')
})

afterEach(() => {
  rmSync(dir, { recursive: true, force: true })
})

describe('readLogIncrement', () => {
  it('文件不存在时返回空且 size 为 0', async () => {
    await expect(readLogIncrement(logPath, 0)).resolves.toEqual({
      content: '',
      size: 0,
      reset: false,
    })
  })

  it('已有偏移但文件消失时标记 reset', async () => {
    await expect(readLogIncrement(logPath, 10)).resolves.toEqual({
      content: '',
      size: 0,
      reset: true,
    })
  })

  it('从 0 起读返回全文并给出字节数', async () => {
    writeFileSync(logPath, 'line1\n中文\n', 'utf-8')
    const first = await readLogIncrement(logPath, 0)
    expect(first).toEqual({
      content: 'line1\n中文\n',
      size: Buffer.byteLength('line1\n中文\n'),
      reset: false,
    })
  })

  it('从上次 size 继续只读新增部分', async () => {
    writeFileSync(logPath, 'line1\n', 'utf-8')
    const first = await readLogIncrement(logPath, 0)
    appendFileSync(logPath, '第二行\n', 'utf-8')
    const second = await readLogIncrement(logPath, first.size)
    expect(second).toEqual({
      content: '第二行\n',
      size: first.size + Buffer.byteLength('第二行\n'),
      reset: false,
    })
  })

  it('文件没有变化时返回空增量', async () => {
    writeFileSync(logPath, 'line1\n', 'utf-8')
    const first = await readLogIncrement(logPath, 0)
    await expect(readLogIncrement(logPath, first.size)).resolves.toEqual({
      content: '',
      size: first.size,
      reset: false,
    })
  })

  it('多字节字符被拆成两次写时不产生乱码', async () => {
    const bytes = Buffer.from('日志\n', 'utf-8')
    writeFileSync(logPath, bytes.subarray(0, 4))
    const first = await readLogIncrement(logPath, 0)
    expect(first).toEqual({ content: '日', size: 3, reset: false })
    appendFileSync(logPath, bytes.subarray(4))
    const second = await readLogIncrement(logPath, first.size)
    expect(second).toEqual({ content: '志\n', size: bytes.length, reset: false })
  })

  it('文件变小（轮转）时返回全文并标记 reset', async () => {
    writeFileSync(logPath, 'a'.repeat(100), 'utf-8')
    const first = await readLogIncrement(logPath, 0)
    unlinkSync(logPath)
    writeFileSync(logPath, 'fresh\n', 'utf-8')
    const rotated = await readLogIncrement(logPath, first.size)
    expect(rotated).toEqual({ content: 'fresh\n', size: 6, reset: true })
  })
})

describe('readLogContent', () => {
  it('文件不存在返回空串', async () => {
    await expect(readLogContent(logPath)).resolves.toBe('')
  })

  it('lines 为 0 或省略返回全文，大于 0 只取最后 N 行', async () => {
    writeFileSync(logPath, 'a\nb\nc', 'utf-8')
    await expect(readLogContent(logPath)).resolves.toBe('a\nb\nc')
    await expect(readLogContent(logPath, 0)).resolves.toBe('a\nb\nc')
    await expect(readLogContent(logPath, 2)).resolves.toBe('b\nc')
  })
})

describe('incompleteUtf8TailLength', () => {
  it('完整序列与 ASCII 结尾返回 0', () => {
    expect(incompleteUtf8TailLength(Buffer.from('abc', 'utf-8'), 3)).toBe(0)
    expect(incompleteUtf8TailLength(Buffer.from('日志', 'utf-8'), 6)).toBe(0)
    expect(incompleteUtf8TailLength(Buffer.alloc(0), 0)).toBe(0)
  })

  it('被截断的两字节、三字节、四字节序列返回已读到的字节数', () => {
    expect(incompleteUtf8TailLength(Buffer.from([0xc3]), 1)).toBe(1)
    const cjk = Buffer.from('日', 'utf-8')
    expect(incompleteUtf8TailLength(cjk, 1)).toBe(1)
    expect(incompleteUtf8TailLength(cjk, 2)).toBe(2)
    const emoji = Buffer.from('😀', 'utf-8')
    expect(incompleteUtf8TailLength(emoji, 3)).toBe(3)
  })
})
