import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  RUNTIME_APP_ENV,
  RUNTIME_HTTPS_PROXY_ENV,
  RUNTIME_HTTP_PROXY_ENV,
  RUNTIME_NO_PROXY_ENV,
  RUNTIME_TELEMETRY_ENV,
  buildRuntimeEnv,
} from './runtimeEnv'

const warn = vi.fn()
const info = vi.fn()

vi.mock('../logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: (...args: unknown[]) => warn(...args),
    info: (...args: unknown[]) => info(...args),
    verbose: vi.fn(),
    debug: vi.fn(),
    silly: vi.fn(),
  }),
}))

let appRoot: string

function writeBackendConfig(value: unknown): void {
  const configDir = path.join(appRoot, 'config')
  fs.mkdirSync(configDir, { recursive: true })
  fs.writeFileSync(path.join(configDir, 'Config.json'), JSON.stringify(value), 'utf8')
}

beforeEach(() => {
  warn.mockClear()
  info.mockClear()
  appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-runtime-env-'))
})

afterEach(() => {
  fs.rmSync(appRoot, { recursive: true, force: true })
})

describe('buildRuntimeEnv', () => {
  it('Config.json 不存在时按开启处理，不设 AUTO_MAS_TELEMETRY', () => {
    expect(buildRuntimeEnv(appRoot)).toEqual({})
    expect(warn).not.toHaveBeenCalled()
  })

  it('IfEnableTelemetry 缺失时按开启处理', () => {
    writeBackendConfig({ Function: {} })

    expect(buildRuntimeEnv(appRoot)).toEqual({})
  })

  it('IfEnableTelemetry 为 true 时按开启处理', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: true } })

    expect(buildRuntimeEnv(appRoot)).toEqual({})
  })

  it('IfEnableTelemetry 为 false 时透传 AUTO_MAS_TELEMETRY=disabled', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })

    expect(buildRuntimeEnv(appRoot)).toEqual({ [RUNTIME_TELEMETRY_ENV]: 'disabled' })
  })

  it('结果里不含任何 offline 相关的键——遥测与联网开关是两回事', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })

    const env = buildRuntimeEnv(appRoot)
    expect(Object.keys(env)).toEqual([RUNTIME_TELEMETRY_ENV])
    expect(env).not.toHaveProperty('offline')
    expect(env).not.toHaveProperty('--offline')
  })

  // JSON.parse('null') 与 JSON.parse('[]') 都是合法的；不排掉的话取字段会抛出去，
  // 打断的正是「初始化卡住」时唯一还能跑的那段。
  it('Config.json 内容为 null 或数组时按缺省处理而不是抛异常', () => {
    const configDir = path.join(appRoot, 'config')
    fs.mkdirSync(configDir, { recursive: true })

    fs.writeFileSync(path.join(configDir, 'Config.json'), 'null', 'utf8')
    expect(() => buildRuntimeEnv(appRoot)).not.toThrow()
    expect(buildRuntimeEnv(appRoot)).toEqual({})

    fs.writeFileSync(path.join(configDir, 'Config.json'), '[]', 'utf8')
    expect(buildRuntimeEnv(appRoot)).toEqual({})
  })

  it('Config.json 损坏时记 warning 并按开启处理', () => {
    const configDir = path.join(appRoot, 'config')
    fs.mkdirSync(configDir, { recursive: true })
    fs.writeFileSync(path.join(configDir, 'Config.json'), '{not json', 'utf8')

    expect(buildRuntimeEnv(appRoot)).toEqual({})
    expect(warn).toHaveBeenCalledOnce()
  })
})

describe('buildRuntimeEnv：出站代理', () => {
  it('配了合法代理时同时透传 HTTP_PROXY / HTTPS_PROXY / NO_PROXY', () => {
    writeBackendConfig({ Update: { ProxyAddress: 'http://127.0.0.1:7890' } })

    expect(buildRuntimeEnv(appRoot)).toEqual({
      [RUNTIME_HTTP_PROXY_ENV]: 'http://127.0.0.1:7890',
      [RUNTIME_HTTPS_PROXY_ENV]: 'http://127.0.0.1:7890',
      [RUNTIME_NO_PROXY_ENV]: '127.0.0.1,localhost,::1',
    })
    expect(warn).not.toHaveBeenCalled()
  })

  it('socks5 代理同样透传', () => {
    writeBackendConfig({ Update: { ProxyAddress: 'socks5://127.0.0.1:1080' } })

    expect(buildRuntimeEnv(appRoot)[RUNTIME_HTTPS_PROXY_ENV]).toBe('socks5://127.0.0.1:1080')
    expect(warn).not.toHaveBeenCalled()
  })

  // 真机上出现过：用户把模拟器安装路径填进了「网络代理」。原样导出会让 Runtime
  // 一条网络路都走不通，比不设代理更糟。
  it('本地路径这类非 URL 值一律忽略并记 warning', () => {
    writeBackendConfig({ Update: { ProxyAddress: 'D:\\虚拟C盘\\MuMuPlayer-12.0\\nx_main' } })

    expect(buildRuntimeEnv(appRoot)).toEqual({})
    expect(warn).toHaveBeenCalledOnce()
  })

  it('协议不在白名单里的一律忽略并记 warning', () => {
    writeBackendConfig({ Update: { ProxyAddress: 'file:///D:/proxy' } })

    expect(buildRuntimeEnv(appRoot)).toEqual({})
    expect(warn).toHaveBeenCalledOnce()
  })

  it('缺少主机名的一律忽略并记 warning', () => {
    writeBackendConfig({ Update: { ProxyAddress: 'http://' } })

    expect(buildRuntimeEnv(appRoot)).toEqual({})
    expect(warn).toHaveBeenCalledOnce()
  })

  it('空串与非字符串按没配处理，不记 warning', () => {
    writeBackendConfig({ Update: { ProxyAddress: '   ' } })
    expect(buildRuntimeEnv(appRoot)).toEqual({})

    writeBackendConfig({ Update: { ProxyAddress: 7890 } })
    expect(buildRuntimeEnv(appRoot)).toEqual({})

    expect(warn).not.toHaveBeenCalled()
  })

  // 后端同一字段的消费者（app/core/config.py 的 GlobalConfig.proxy）一直会给不带协议的
  // 地址补 http://。这里不补的话，用户填 127.0.0.1:7890 会出现「更新检查走了代理、
  // Runtime 仍在裸连」，正是本改动要消灭的现象。
  it('不带协议的地址补 http:// 后透传，与后端口径一致', () => {
    writeBackendConfig({ Update: { ProxyAddress: '127.0.0.1:7890' } })

    expect(buildRuntimeEnv(appRoot)[RUNTIME_HTTPS_PROXY_ENV]).toBe('http://127.0.0.1:7890')
    expect(warn).not.toHaveBeenCalled()
  })

  it('不带协议的域名同样补 http://', () => {
    writeBackendConfig({ Update: { ProxyAddress: 'proxy.example.com:8080' } })

    expect(buildRuntimeEnv(appRoot)[RUNTIME_HTTPS_PROXY_ENV]).toBe('http://proxy.example.com:8080')
  })

  // 后端放行 socks4，但 Go 的 ProxyFromEnvironment 不支持，这里必须拒绝。
  it('socks4 仍然拒绝', () => {
    writeBackendConfig({ Update: { ProxyAddress: 'socks4://127.0.0.1:1080' } })

    expect(buildRuntimeEnv(appRoot)).toEqual({})
    expect(warn).toHaveBeenCalledOnce()
  })

  // frontend.log 会被用户直接贴进 issue。
  it('日志里遮蔽代理地址中的凭据，环境变量本身仍是原值', () => {
    writeBackendConfig({ Update: { ProxyAddress: 'http://user:secret@127.0.0.1:7890' } })

    const env = buildRuntimeEnv(appRoot)
    expect(env[RUNTIME_HTTPS_PROXY_ENV]).toBe('http://user:secret@127.0.0.1:7890')

    const logged = info.mock.calls.map(call => String(call[0])).join('\n')
    expect(logged).toContain('http://***@127.0.0.1:7890')
    expect(logged).not.toContain('secret')
  })

  it('代理与遥测开关互不影响', () => {
    writeBackendConfig({
      Function: { IfEnableTelemetry: false },
      Update: { ProxyAddress: 'http://127.0.0.1:7890' },
    })

    const env = buildRuntimeEnv(appRoot)
    expect(env[RUNTIME_TELEMETRY_ENV]).toBe('disabled')
    expect(env[RUNTIME_HTTPS_PROXY_ENV]).toBe('http://127.0.0.1:7890')
  })
})

describe('buildRuntimeEnv：开发标记', () => {
  it('development 模式追加 AUTO_MAS_ENV=development', () => {
    expect(buildRuntimeEnv(appRoot, 'development')).toEqual({ [RUNTIME_APP_ENV]: 'development' })
  })

  it('development 模式且关闭遥测时两项同时透传', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })

    expect(buildRuntimeEnv(appRoot, 'development')).toEqual({
      [RUNTIME_TELEMETRY_ENV]: 'disabled',
      [RUNTIME_APP_ENV]: 'development',
    })
  })

  it('managed / off / 未指定模式都不碰 AUTO_MAS_ENV', () => {
    expect(buildRuntimeEnv(appRoot, 'managed')).toEqual({})
    expect(buildRuntimeEnv(appRoot, 'off')).toEqual({})
    expect(buildRuntimeEnv(appRoot)).toEqual({})
  })
})
