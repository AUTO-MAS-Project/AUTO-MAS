import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  addDebugDirectory,
  addDiagnosticFile,
  CollectorState,
  maskVerbatimJsonText,
} from './issueReportCore'

vi.mock('./logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    verbose: vi.fn(),
    debug: vi.fn(),
    silly: vi.fn(),
  }),
}))

let root: string

function write(relative: string, text: string): void {
  const target = path.join(root, relative)
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, text, 'utf-8')
}

function collect(archiveDir: string, ownAdapter?: 'oknte'): CollectorState['entries'] {
  const state: CollectorState = { zip: new AdmZip(), entries: [], archiveBytes: 0 }
  addDebugDirectory(state, path.join(root, 'debug'), archiveDir, ownAdapter)
  return state.entries
}

function pathsOf(entries: ReturnType<typeof collect>): string[] {
  return entries.map(entry => entry.path)
}

function skippedPaths(entries: ReturnType<typeof collect>): string[] {
  return entries.filter(entry => entry.status === 'skipped').map(entry => entry.path)
}

describe('addDebugDirectory 只收声明方自己的诊断子目录', () => {
  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'issue-report-core-'))
  })

  afterEach(() => {
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('收顶层文件与 ownAdapter 声明的目录，其他专项与未登记目录都跳过', () => {
    write('debug/app.log', 'app log')
    write('debug/oknte-launcher-start/launcher-error.jpg', 'oknte')
    write('debug/maaend-login/login-error.jpg', 'maaend')
    write('debug/okww-account-switch/switch-error.jpg', 'okww')
    write('debug/new-adapter-diag/detail.log', '未登记的新目录')

    const entries = collect('logs/auto-mas', 'oknte')

    expect(pathsOf(entries)).toContain('logs/auto-mas/app.log')
    expect(pathsOf(entries)).toContain('logs/auto-mas/oknte-launcher-start/launcher-error.jpg')
    expect(pathsOf(entries)).not.toContain('logs/auto-mas/maaend-login/login-error.jpg')
    expect(pathsOf(entries)).not.toContain('logs/auto-mas/okww-account-switch/switch-error.jpg')
    expect(pathsOf(entries)).not.toContain('logs/auto-mas/new-adapter-diag/detail.log')
  })

  it('其他专项的登记目录静默跳过，未登记目录留跳过条目进清单', () => {
    write('debug/maaend-login/login-error.jpg', 'maaend')
    write('debug/new-adapter-diag/detail.log', '未登记的新目录')

    const entries = collect('logs/auto-mas', 'oknte')

    expect(skippedPaths(entries)).toEqual(['logs/auto-mas/new-adapter-diag'])
    expect(skippedPaths(entries)).not.toContain('logs/auto-mas/maaend-login')
  })

  it('未声明 ownAdapter 时只收顶层文件', () => {
    write('debug/app.log', 'app log')
    write('debug/maaend-login/login-error.jpg', 'maaend')
    write('debug/oknte-launcher-start/launcher-error.jpg', 'oknte')

    const entries = collect('logs/auto-mas')

    expect(pathsOf(entries)).toEqual(['logs/auto-mas/app.log'])
  })
})

describe('maskVerbatimJsonText 原文打码', () => {
  // 这里的输入一律用普通字符串写转义（'\\u002F' 是原文里的六个字符），不用 String.raw：
  // 转译后 String.raw 里的 \u 转义会被解码，测不到原文里的转义写法
  const HOME = 'C:\\Users\\tester'
  const mask = (text: string) => maskVerbatimJsonText(text, HOME)

  it('字符串里 \\/ 转义写法的推送地址照样打码，只换这一个字面量', () => {
    const text = '{ "a": "https:\\/\\/api.day.app\\/SECRET_A", "keep": "x\\/y" }'
    expect(text).toContain('https:\\/\\/')
    expect(mask(text)).toBe('{ "a": "https://api.day.app/***", "keep": "x\\/y" }')
  })

  it('\\u002F 大小写两种写法都认得出', () => {
    const upper = '["https:\\u002F\\u002Fapi.day.app\\u002FSECRET_B"]'
    const lower = '["https:\\u002f\\u002fapi.day.app\\u002fSECRET_C"]'
    expect(upper).toContain('\\u002F')
    expect(lower).toContain('\\u002f')
    expect(mask(upper)).toBe('["https://api.day.app/***"]')
    expect(mask(lower)).toBe('["https://api.day.app/***"]')
  })

  it('其他 \\uXXXX 转义写成的地址也认得出', () => {
    const text = '["\\u0068ttps://\\u0061pi.day.app/SECRET_I"]'
    expect(mask(text)).toBe('["https://api.day.app/***"]')
  })

  it('普通写法的地址与注释里的地址都打码', () => {
    const text = [
      '{',
      '  // 推送 https://api.day.app/SECRET_D',
      '  /* 备用 https://api.day.app/SECRET_E */',
      '  "url": "https://api.day.app/SECRET_F"',
      '}',
    ].join('\n')
    expect(mask(text)).toBe(text.replace(/SECRET_[DEF]/g, '***'))
  })

  it('主目录的原样、JSON 转义、正斜杠三种写法都换成 <HOME>', () => {
    const text = [
      '{ "a": "C:\\\\Users\\\\tester\\\\proj", "b": "C:/Users/tester/proj" }',
      '// 原样 C:\\Users\\tester\\raw',
    ].join('\n')
    expect(text).toContain('C:\\\\Users\\\\tester')
    const masked = mask(text)
    expect(masked).not.toContain('tester')
    expect(masked.match(/<HOME>/g)).toHaveLength(3)
  })

  it('不含密钥的 JSONC 逐字节不变（注释、格式、其他转义都保留）', () => {
    const text = [
      '{',
      '  // 项目说明',
      '  "name": "Demo\\u0020项目",',
      '  "resource": [{ "path": ["./resource\\/base"] }], /* 尾注 */',
      '  "github": "https://github.com/owner/repo"',
      '}',
      '',
    ].join('\r\n')
    expect(text).toContain('\\u0020')
    expect(mask(text)).toBe(text)
  })

  it('坏字面量不抛错，按原文打码', () => {
    const text =
      '{ "a": "bad \\x https://api.day.app/SECRET_G", "b": "未闭合 https://api.day.app/SECRET_H\n}'
    let masked = ''
    expect(() => {
      masked = mask(text)
    }).not.toThrow()
    expect(masked).not.toMatch(/SECRET_[GH]/)
    expect(mask('"')).toBe('"')
    expect(mask('"\\')).toBe('"\\')
  })
})

describe('addDiagnosticFile 收解析不了的 .json', () => {
  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'issue-report-core-'))
  })

  afterEach(() => {
    fs.rmSync(root, { recursive: true, force: true })
  })

  const collectText = (relative: string) => {
    const state: CollectorState = { zip: new AdmZip(), entries: [], archiveBytes: 0 }
    addDiagnosticFile(state, path.join(root, relative), 'out/file.json')
    return state.zip.getEntry('out/file.json')!.getData().toString('utf-8')
  }

  it('带注释的 .json 里转义写法与普通写法的推送地址都打码，按键名的打码照旧', () => {
    // 普通字符串写转义：'\\/' 与 '\\u002F' 是原文里的反斜杠转义
    const text = [
      '{',
      '  // 注释 https://api.day.app/SECRET_K',
      '  "a": "https:\\/\\/api.day.app\\/SECRET_L",',
      '  "b": "https:\\u002F\\u002Fapi.day.app\\u002fSECRET_M",',
      '  "c": "https://api.day.app/SECRET_N",',
      '  "password": "SECRET_O"',
      '}',
    ].join('\n')
    expect(text).toContain('\\u002F')
    write('debug/conf.json', text)

    const stored = collectText('debug/conf.json')

    expect(stored).not.toMatch(/SECRET_[KLMNO]/)
    expect(stored).toContain('// 注释 https://api.day.app/***')
    expect(stored).toContain('"a": "https://api.day.app/***"')
  })

  it('能解析的 .json 照旧按键名打码并重新排版', () => {
    write('debug/plain.json', '{"b":"https:\\/\\/api.day.app\\/SECRET_P","token":"t"}')

    expect(collectText('debug/plain.json')).toBe(
      `${JSON.stringify({ b: 'https://api.day.app/***', token: '***' }, null, 2)}\n`
    )
  })
})
