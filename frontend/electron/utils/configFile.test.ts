import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { clearAppearanceConfigIfCurrent, patchConfigFile } from './configFile'

vi.mock('fs', async importOriginal => {
  const actual = await importOriginal<typeof import('fs')>()
  return { ...actual, renameSync: vi.fn(actual.renameSync) }
})

let testRoot: string
let configPath: string

beforeEach(() => {
  testRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-config-patch-'))
  configPath = path.join(testRoot, 'config', 'frontend_config.json')
})

afterEach(() => {
  if (
    path.dirname(testRoot) !== path.resolve(os.tmpdir()) ||
    !path.basename(testRoot).startsWith('auto-mas-config-patch-')
  ) {
    throw new Error('测试清理目录超出临时目录')
  }
  fs.rmSync(testRoot, { recursive: true, force: true })
})

const readConfig = () => JSON.parse(fs.readFileSync(configPath, 'utf8'))

describe('主进程配置补丁写入', () => {
  it('损坏的配置会拒绝写入并保留原文件，修复后可重试', () => {
    const fallback = {
      UI: { location: '100,100', size: '1600,1000' },
      Runtime: { LaunchMode: 'auto' },
      custom: 'previous',
    }
    fs.mkdirSync(path.dirname(configPath), { recursive: true })
    fs.writeFileSync(configPath, '{broken', 'utf8')

    expect(() => patchConfigFile(configPath, { language: 'en-US' }, fallback)).toThrow()
    expect(fs.readFileSync(configPath, 'utf8')).toBe('{broken')
    fs.writeFileSync(
      configPath,
      JSON.stringify({
        themeColor: 'green',
        UI: { location: '200,300', size: '1200,900' },
        Runtime: { LaunchMode: 'on' },
        custom: 'latest',
      }),
      'utf8'
    )
    patchConfigFile(configPath, { language: 'en-US' }, fallback)
    expect(readConfig()).toEqual({
      language: 'en-US',
      themeColor: 'green',
      UI: { location: '200,300', size: '1200,900' },
      Runtime: { LaunchMode: 'on' },
      custom: 'latest',
    })
    expect(fs.readdirSync(path.dirname(configPath))).toEqual([path.basename(configPath)])
  })

  it.each(['[]', 'null', '"text"', '42', 'false'])('拒绝覆盖非对象 JSON %s', raw => {
    fs.mkdirSync(path.dirname(configPath), { recursive: true })
    fs.writeFileSync(configPath, raw, 'utf8')

    expect(() => patchConfigFile(configPath, { language: 'en-US' })).toThrow('JSON 对象')
    expect(() => clearAppearanceConfigIfCurrent(configPath, 'old', () => true)).toThrow('JSON 对象')
    expect(fs.readFileSync(configPath, 'utf8')).toBe(raw)
  })

  it('外观清理替换失败时保留原文件、清理临时文件，并可重试', () => {
    const original = { appearanceId: 'old', themeColor: 'green' }
    const updated = { ...original, appearanceId: null }
    fs.mkdirSync(path.dirname(configPath), { recursive: true })
    fs.writeFileSync(configPath, JSON.stringify(original), 'utf8')
    vi.mocked(fs.renameSync).mockImplementationOnce(tempPath => {
      expect(path.dirname(String(tempPath))).toBe(path.dirname(configPath))
      expect(JSON.parse(fs.readFileSync(tempPath, 'utf8'))).toEqual(updated)
      expect(readConfig()).toEqual(original)
      throw new Error('目标文件被占用')
    })

    expect(() => clearAppearanceConfigIfCurrent(configPath, 'old', () => true)).toThrow(
      '目标文件被占用'
    )
    expect(readConfig()).toEqual(original)
    expect(fs.readdirSync(path.dirname(configPath))).toEqual([path.basename(configPath)])

    expect(clearAppearanceConfigIfCurrent(configPath, 'old', () => true).cleared).toBe(true)
    expect(readConfig()).toEqual(updated)
    expect(fs.readdirSync(path.dirname(configPath))).toEqual([path.basename(configPath)])
  })
})
