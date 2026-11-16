import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vite-plus/test'
import { patchConfigFile } from './configFile'

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
  })
})
