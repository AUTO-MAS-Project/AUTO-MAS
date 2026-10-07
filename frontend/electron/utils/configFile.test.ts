import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { clearAppearanceConfigIfCurrent, patchConfigFile } from './configFile'

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
  it('清理旧外观不会覆盖另一窗口刚持久化的新外观', () => {
    patchConfigFile(configPath, { appearanceId: 'x', UI: { location: '100,100' } })
    patchConfigFile(configPath, { appearanceId: 'y' })

    const result = clearAppearanceConfigIfCurrent(configPath, 'x', () => true)

    expect(result.cleared).toBe(false)
    expect(result.config.appearanceId).toBe('y')
    expect(readConfig()).toEqual({ appearanceId: 'y', UI: { location: '100,100' } })
  })

  it('同步清理当前失效外观并保留所有其他配置字段', () => {
    patchConfigFile(configPath, { appearanceId: 'x', themeColor: 'green', custom: 'preserved' })

    const result = clearAppearanceConfigIfCurrent(configPath, 'x', () => true)

    expect(result).toEqual({
      cleared: true,
      config: { appearanceId: null, themeColor: 'green', custom: 'preserved' },
    })
    expect(readConfig()).toEqual(result.config)
  })

  it('有效包和缺失配置文件都不触发写入', () => {
    expect(clearAppearanceConfigIfCurrent(configPath, 'x', () => true)).toEqual({
      cleared: false,
      config: {},
    })
    expect(fs.existsSync(configPath)).toBe(false)
    patchConfigFile(configPath, { appearanceId: 'x' })
    expect(clearAppearanceConfigIfCurrent(configPath, 'x', () => false).cleared).toBe(false)
    expect(readConfig()).toEqual({ appearanceId: 'x' })
  })

  it('保存偏好保留磁盘最新的窗口、Runtime 和未知字段', () => {
    const previous = {
      UI: { location: '100,100', size: '1600,1000' },
      Runtime: { LaunchMode: 'auto' },
      custom: 'previous',
    }
    patchConfigFile(configPath, previous)
    patchConfigFile(configPath, {
      UI: { location: '200,300', size: '1200,900' },
      Runtime: { LaunchMode: 'on' },
      custom: 'latest',
    })

    patchConfigFile(configPath, { language: 'en-US' }, previous)

    expect(readConfig()).toEqual({
      language: 'en-US',
      UI: { location: '200,300', size: '1200,900' },
      Runtime: { LaunchMode: 'on' },
      custom: 'latest',
    })
  })

  it('补丁写入后主进程同步保存窗口状态，偏好仍保留', () => {
    patchConfigFile(configPath, { language: 'en-US' })
    const current = readConfig()
    current.UI = { location: '200,300' }
    fs.writeFileSync(configPath, JSON.stringify(current), 'utf8')

    expect(readConfig()).toEqual({ language: 'en-US', UI: { location: '200,300' } })
  })

  it('迁移仅补齐缺失字段，保留当前文件中的值', () => {
    patchConfigFile(configPath, { themeColor: 'green', UI: { location: '200,300' } })

    const saved = patchConfigFile(
      configPath,
      {},
      { language: 'en-US', themeColor: 'blue', UI: { location: '100,100' } }
    )

    expect(saved).toEqual({ language: 'en-US', themeColor: 'green', UI: { location: '200,300' } })
    expect(readConfig()).toEqual(saved)
  })

  it('文件缺失时创建目录，保存默认值和旧版偏好', () => {
    patchConfigFile(configPath, { themeColor: 'green' }, { language: 'en-US', themeMode: 'dark' })

    expect(readConfig()).toEqual({ themeColor: 'green', language: 'en-US', themeMode: 'dark' })
  })

  it('显式补丁允许空字符串、false 和空数组，替换整个字段', () => {
    patchConfigFile(configPath, { label: 'old', enabled: true, selected: ['old'] })
    patchConfigFile(configPath, { label: '', enabled: false, selected: [] })

    expect(readConfig()).toEqual({ label: '', enabled: false, selected: [] })
  })

  it('损坏的配置会拒绝写入并保留原文件，修复后可重试', () => {
    fs.mkdirSync(path.dirname(configPath), { recursive: true })
    fs.writeFileSync(configPath, '{broken', 'utf8')

    expect(() => patchConfigFile(configPath, { language: 'en-US' })).toThrow()
    expect(fs.readFileSync(configPath, 'utf8')).toBe('{broken')
    fs.writeFileSync(configPath, '{"themeColor":"green"}', 'utf8')
    patchConfigFile(configPath, { language: 'en-US' })
    expect(readConfig()).toEqual({ language: 'en-US', themeColor: 'green' })
  })
})
