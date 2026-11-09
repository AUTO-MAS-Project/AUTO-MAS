import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { readBackendDocument } from './backendConfig'
import { buildRuntimeEnv } from './runtime/runtimeEnv'

vi.mock('./logger', () => ({ getLogger: () => ({ warn: vi.fn() }) }))

let root: string

function write(name: string, text: string): void {
  fs.writeFileSync(path.join(root, 'config', name), text, 'utf8')
}

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-yaml-reader-'))
  fs.mkdirSync(path.join(root, 'config'))
})

afterEach(() => fs.rmSync(root, { recursive: true, force: true }))

describe('配置升级前后的 Electron 文件读取', () => {
  it('首次升级可读 JSON，并转换嵌套集合索引', () => {
    write(
      'ScriptConfig.json',
      JSON.stringify({
        instances: [{ uid: 'script', type: 'GeneralConfig' }],
        script: {
          SubConfigsInfo: {
            UserData: {
              instances: [{ uid: 'user', type: 'GeneralUserConfig' }],
              user: { Info: { Name: 'account' } },
            },
          },
        },
      })
    )
    expect(readBackendDocument(root, 'scripts.yaml', 'ScriptConfig.json')).toEqual({
      order: [{ uid: 'script', type: 'GeneralConfig' }],
      data: {
        script: {
          UserData: {
            order: [{ uid: 'user', type: 'GeneralUserConfig' }],
            data: { user: { Info: { Name: 'account' } } },
          },
        },
      },
    })
  })

  it('YAML 优先于旧 JSON，遥测设置传入 Runtime', () => {
    write('Config.json', JSON.stringify({ Function: { IfEnableTelemetry: true } }))
    write('setting.yaml', 'Function:\n  IfEnableTelemetry: false\n')
    expect(buildRuntimeEnv(root)).toMatchObject({ AUTO_MAS_TELEMETRY: 'disabled' })
  })

  it('迁移完成后，缺少 YAML 也不重新导入 JSON', () => {
    write('.config-migration-v2.json', JSON.stringify({ version: 2, complete: true }))
    write('Config.json', JSON.stringify({ Function: { IfEnableTelemetry: false } }))
    expect(readBackendDocument(root, 'setting.yaml', 'Config.json')).toBeUndefined()
  })

  it('已有 YAML 损坏时不退回旧 JSON', () => {
    write('setting.yaml', 'Function: [broken')
    write('Config.json', JSON.stringify({ Function: { IfEnableTelemetry: false } }))
    expect(readBackendDocument(root, 'setting.yaml', 'Config.json')).toBeUndefined()
  })
})
