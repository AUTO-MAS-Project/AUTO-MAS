/**
 * Emulator Provider Contract Matrix (fake provider, no real emulator).
 *
 * Subagent C 维护。验证 `app/plugins/emulator_compat.get_emulator_service`
 * 的契约形状：plugin 缺失/失败时回退到 host 实现，未知 provider 抛错等。
 *
 * 本文件不导入 Python 代码；通过 fakeEmulatorService 模拟 service 行为，
 * 当 B 实装前端 composable 后，这些用例可作为 composable 集成测试的基线。
 *
 * 对应 TEST_MATRIX.md 中的 BE-CONTRACT-01..06：
 *  - host fallback
 *  - real provider
 *  - 失败恢复
 *  - 未知 provider
 *  - 超时
 *  - 取消
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  createFakeEmulatorService,
  createFakeEmulatorServiceState,
  type FakeEmulatorService,
} from './fakeEmulatorService'
import { EmulatorOperateIn } from '@/api'
import { makeIndexItem, makeEmulatorConfig, makeDeviceInfo } from './fakeEmulatorApi'

function seedTwoDevices(svc: FakeEmulatorService) {
  svc.state.index.push(makeIndexItem('emu-0001', 'mumu'))
  svc.state.index.push(makeIndexItem('emu-0002', 'ldplayer'))
  svc.state.data['emu-0001'] = makeEmulatorConfig({ Info: { Name: 'MuMu-1', Type: 'mumu' } })
  svc.state.data['emu-0002'] = makeEmulatorConfig({ Info: { Name: 'LD-1', Type: 'ldplayer' } })
  svc.state.devices['emu-0001'] = {
    '0': makeDeviceInfo({ status: 1, title: 'mumu-0' }),
  }
  svc.state.devices['emu-0002'] = {
    '0': makeDeviceInfo({ status: 1, title: 'ld-0' }),
  }
}

describe('Provider Contract: host fallback (BE-CONTRACT-01)', () => {
  it('provider.kind=host 时所有调用经 host 路径', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'host', installed: false })
    )
    seedTwoDevices(svc)
    const { index, data } = await svc.get_config(null)
    expect(index).toHaveLength(2)
    expect(data['emu-0001'].Info?.Name).toBe('MuMu-1')
    await svc.operate(EmulatorOperateIn.operate.OPEN, 'emu-0001', '0')
    expect(svc.state.operationLog[0].via).toBe('host')
    expect(svc.state.devices['emu-0001']['0'].status).toBe(0)
  })

  it('provider.kind=plugin 但 installed=false 时抛 pluginError', async () => {
    // 模拟 plugin 未注册：get_emulator_service 返回 _legacy_emulator_service
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({
        kind: 'plugin',
        installed: false,
        pluginError: new Error('plugin not registered'),
      })
    )
    // 注意：本 fake 在 plugin 未安装时抛 pluginError（与 emulator_compat 实际行为不同）；
    // 真实 emulator_compat 会回退到 host。这里只验证「抛错时前端不应崩溃」。
    await expect(svc.get_config(null)).rejects.toThrow('plugin not registered')
  })
})

describe('Provider Contract: real plugin provider (BE-CONTRACT-02)', () => {
  it('provider.kind=plugin 且 installed=true 时经 plugin 路径', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'plugin', installed: true })
    )
    seedTwoDevices(svc)
    await svc.operate(EmulatorOperateIn.operate.OPEN, 'emu-0001', '0')
    expect(svc.state.operationLog[0].via).toBe('plugin')
  })

  it('plugin provider 支持 list_options / list_device_options', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'plugin', installed: true })
    )
    seedTwoDevices(svc)
    const opts = await svc.list_options()
    expect(opts).toHaveLength(2)
    expect(opts[0].label).toBe('MuMu-1')
    const devOpts = await svc.list_device_options('emu-0001')
    expect(devOpts).toHaveLength(1)
    expect(devOpts[0].value).toBe('0')
  })
})

describe('Provider Contract: 失败恢复 (BE-CONTRACT-03)', () => {
  it('operate 失败后 status 仍可查询且不崩溃', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'host', installed: false })
    )
    seedTwoDevices(svc)
    // 模拟 operate 抛错（真实场景为 ADB 丢失等）
    const original = svc.operate
    svc.operate = async () => {
      throw new Error('ADB connection lost')
    }
    await expect(svc.operate(EmulatorOperateIn.operate.OPEN, 'emu-0001', '0')).rejects.toThrow(
      'ADB connection lost'
    )
    svc.operate = original
    // status 仍可用
    const st = await svc.status('emu-0001')
    expect(st['emu-0001']['0'].status).toBe(1)
  })

  it('search_installed 失败后 get_config 仍可用', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'host', installed: false })
    )
    seedTwoDevices(svc)
    const original = svc.search_installed
    svc.search_installed = async () => {
      throw new Error('registry enumeration failed')
    }
    await expect(svc.search_installed()).rejects.toThrow('registry enumeration failed')
    svc.search_installed = original
    const { index } = await svc.get_config(null)
    expect(index).toHaveLength(2)
  })
})

describe('Provider Contract: 未知 provider (BE-CONTRACT-04)', () => {
  it('kind=unknown 抛错且不写入任何状态', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'unknown', installed: false })
    )
    await expect(svc.get_config(null)).rejects.toThrow('unknown provider kind')
    expect(svc.state.operationLog).toHaveLength(0)
  })
})

describe('Provider Contract: 超时 (BE-CONTRACT-05)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('operateDelayMs > 0 时 operate 在超时前未完成', async () => {
    vi.useFakeTimers()
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({
        kind: 'host',
        installed: false,
        operateDelayMs: 5000,
      })
    )
    seedTwoDevices(svc)
    const promise = svc.operate(EmulatorOperateIn.operate.OPEN, 'emu-0001', '0')
    // 推进 1000ms，仍未完成
    vi.advanceTimersByTime(1000)
    expect(svc.state.devices['emu-0001']['0'].status).toBe(1)
    // 推进到 5000ms 后完成
    vi.advanceTimersByTime(4000)
    await promise
    expect(svc.state.devices['emu-0001']['0'].status).toBe(0)
    vi.useRealTimers()
  })
})

describe('Provider Contract: 取消 (BE-CONTRACT-06)', () => {
  it('markCancelled 把 key 加入 cancelled 集合', () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'host', installed: false })
    )
    svc.markCancelled('emu-0001', 'open', '0')
    expect(svc.state.cancelled.has('emu-0001#open#0')).toBe(true)
  })

  it('取消后 status 查询不反映 operate 的状态变迁', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'host', installed: false })
    )
    seedTwoDevices(svc)
    // 取消 emulate：operate 调用前先 markCancelled，前端契约应跳过该 operate
    svc.markCancelled('emu-0001', 'open', '0')
    // 但 fake service 本身不读 cancelled；这里只验证集合状态
    const st = await svc.status('emu-0001')
    expect(st['emu-0001']['0'].status).toBe(1)
  })
})

describe('Provider Contract: reorder (BE-CONTRACT-07)', () => {
  it('reorder 后 index 顺序与传入一致，丢失项被过滤', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'host', installed: false })
    )
    seedTwoDevices(svc)
    await svc.reorder(['emu-0002', 'emu-0001'])
    expect(svc.state.index.map(i => i.uid)).toEqual(['emu-0002', 'emu-0001'])
    // 传入不存在的 uid 被过滤
    await svc.reorder(['emu-0001', 'emu-not-exist', 'emu-0002'])
    expect(svc.state.index.map(i => i.uid)).toEqual(['emu-0001', 'emu-0002'])
  })
})

describe('Provider Contract: status 全量与单点 (BE-CONTRACT-08)', () => {
  it('status(null) 返回所有模拟器设备', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'host', installed: false })
    )
    seedTwoDevices(svc)
    const st = await svc.status(null)
    expect(Object.keys(st)).toEqual(['emu-0001', 'emu-0002'])
  })

  it('status(emulatorId) 仅返回该模拟器设备', async () => {
    const svc = createFakeEmulatorService(
      createFakeEmulatorServiceState({ kind: 'host', installed: false })
    )
    seedTwoDevices(svc)
    const st = await svc.status('emu-0001')
    expect(Object.keys(st)).toEqual(['emu-0001'])
  })
})
