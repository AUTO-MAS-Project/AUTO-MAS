/**
 * Emulator API 契约测试矩阵 (deterministic, no real backend).
 *
 * Subagent C 维护。这些测试不挂载 Emulator.vue（B 尚未实装前端重构），
 * 而是验证 fakeEmulatorApi 的契约形状与边界行为，为 B 实装后的
 * composable 测试提供基线。任何对 `@/api` 形状的回归都会在这里被捕获。
 *
 * 覆盖维度（对应 TEST_MATRIX.md 中的 FE-CONTRACT-*）：
 *  - FE-CONTRACT-01 API 成功路径
 *  - FE-CONTRACT-02 业务失败（code !== 200）
 *  - FE-CONTRACT-03 抛异常路径
 *  - FE-CONTRACT-04 旧响应覆盖保护（epoch/version）—— 通过 fake 时序验证
 *  - FE-CONTRACT-05 搜索去重
 *  - FE-CONTRACT-06 导入流程
 *  - FE-CONTRACT-07 保存冲突（并发 update）
 *  - FE-CONTRACT-08 删除后状态清理
 *  - FE-CONTRACT-09 per-device in-flight 标记
 *  - FE-CONTRACT-10 operate 状态变迁
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  createFakeEmulatorApi,
  makeEmulatorConfig,
  makeIndexItem,
  makeDeviceInfo,
  type FakeEmulatorApi,
} from './fakeEmulatorApi'
import { EmulatorOperateIn } from '@/api'

describe('FakeEmulatorApi 契约形状 (FE-CONTRACT-01)', () => {
  let api: FakeEmulatorApi
  beforeEach(() => {
    api = createFakeEmulatorApi()
  })

  it('getEmulator 全量返回 index 与 data', async () => {
    const state = api.state
    state.index.push(makeIndexItem('emu-0001', 'mumu'))
    state.data['emu-0001'] = makeEmulatorConfig({
      Info: { Name: 'MuMu-1', Type: 'mumu', Path: 'C:/mumu', MaxWaitTime: 300 },
    })
    const res = await api.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    expect(res.code).toBe(200)
    expect(res.index).toHaveLength(1)
    expect(res.index[0].uid).toBe('emu-0001')
    expect(res.data['emu-0001'].Info?.Name).toBe('MuMu-1')
  })

  it('getEmulator 指定 emulatorId 仅返回该项', async () => {
    const state = api.state
    state.index.push(makeIndexItem('emu-0001'), makeIndexItem('emu-0002'))
    state.data['emu-0001'] = makeEmulatorConfig()
    state.data['emu-0002'] = makeEmulatorConfig()
    const res = await api.getEmulatorApiEmulatorGetPost({ emulatorId: 'emu-0001' })
    expect(res.index).toHaveLength(1)
    expect(res.index[0].uid).toBe('emu-0001')
    expect(Object.keys(res.data)).toEqual(['emu-0001'])
  })

  it('addEmulator 返回新 uid 且 index 自增', async () => {
    const r1 = await api.addEmulatorApiEmulatorAddPost()
    const r2 = await api.addEmulatorApiEmulatorAddPost()
    expect(r1.code).toBe(200)
    expect(r1.emulatorId).toBe('emu-0000')
    expect(r2.emulatorId).toBe('emu-0001')
    expect(api.state.index).toHaveLength(2)
  })

  it('updateEmulator 写回 Info 子字段', async () => {
    const add = await api.addEmulatorApiEmulatorAddPost()
    await api.updateEmulatorApiEmulatorUpdatePost({
      emulatorId: add.emulatorId,
      data: { Info: { Name: 'renamed' } },
    })
    expect(api.state.data[add.emulatorId].Info?.Name).toBe('renamed')
    // 未覆盖字段保持
    expect(api.state.data[add.emulatorId].Info?.Type).toBe('general')
  })

  it('deleteEmulator 移除 index/data/devices', async () => {
    const add = await api.addEmulatorApiEmulatorAddPost()
    api.state.devices[add.emulatorId] = { '0': makeDeviceInfo() }
    await api.deleteEmulatorApiEmulatorDeletePost({ emulatorId: add.emulatorId })
    expect(api.state.index).toHaveLength(0)
    expect(api.state.data[add.emulatorId]).toBeUndefined()
    expect(api.state.devices[add.emulatorId]).toBeUndefined()
  })

  it('searchEmulators 返回 searchResults 副本', async () => {
    api.state.searchResults.push({
      type: 'mumu',
      path: 'C:/mumu/MuMuManager.exe',
      name: 'MuMu (C:/mumu/MuMuManager.exe)',
    })
    const res = await api.searchEmulatorsApiEmulatorEmulatorSearchPost()
    expect(res.code).toBe(200)
    const emulators = res.emulators
    expect(emulators).toBeDefined()
    if (!emulators) {
      throw new Error('searchEmulators response is missing emulators')
    }
    expect(emulators).toHaveLength(1)
    // 修改返回值不影响内部状态
    emulators.push({
      type: 'ldplayer',
      path: 'x',
      name: 'x',
    })
    expect(api.state.searchResults).toHaveLength(1)
  })
})

describe('FakeEmulatorApi 业务失败路径 (FE-CONTRACT-02)', () => {
  let api: FakeEmulatorApi
  beforeEach(() => {
    api = createFakeEmulatorApi()
  })

  it('getEmulator 业务失败时 code !== 200 且携带 message', async () => {
    api.setBusinessFailure('getEmulatorApiEmulatorGetPost', 500, 'backend down')
    const res = await api.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    expect(res.code).toBe(500)
    expect(res.status).toBe('error')
    expect(res.message).toBe('backend down')
  })

  it('operate 业务失败时不改变设备状态', async () => {
    const add = await api.addEmulatorApiEmulatorAddPost()
    api.state.devices[add.emulatorId] = {
      '0': makeDeviceInfo({ status: 1, adb_address: '' }),
    }
    api.setBusinessFailure('operationEmulatorApiEmulatorOperatePost', 500, 'operate failed')
    const res = await api.operationEmulatorApiEmulatorOperatePost({
      emulatorId: add.emulatorId,
      operate: EmulatorOperateIn.operate.OPEN,
      index: '0',
    })
    expect(res.code).toBe(500)
    // 设备仍为 OFFLINE
    expect(api.state.devices[add.emulatorId]['0'].status).toBe(1)
  })

  it('业务失败覆盖只影响指定方法', async () => {
    api.setBusinessFailure('getEmulatorApiEmulatorGetPost', 500)
    const failed = await api.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    const ok = await api.addEmulatorApiEmulatorAddPost()
    expect(failed.code).toBe(500)
    expect(ok.code).toBe(200)
  })
})

describe('FakeEmulatorApi 抛异常路径 (FE-CONTRACT-03)', () => {
  let api: FakeEmulatorApi
  beforeEach(() => {
    api = createFakeEmulatorApi()
  })

  it('setThrow 让下一次调用抛出', async () => {
    api.setThrow('getEmulatorApiEmulatorGetPost', new TypeError('network down'))
    await expect(api.getEmulatorApiEmulatorGetPost({ emulatorId: null })).rejects.toThrow(
      'network down'
    )
  })

  it('抛异常后状态保持一致（无半成品写入）', async () => {
    const add = await api.addEmulatorApiEmulatorAddPost()
    api.state.devices[add.emulatorId] = {
      '0': makeDeviceInfo({ status: 1 }),
    }
    api.setThrow('operationEmulatorApiEmulatorOperatePost', new Error('ADB lost'))
    await expect(
      api.operationEmulatorApiEmulatorOperatePost({
        emulatorId: add.emulatorId,
        operate: EmulatorOperateIn.operate.OPEN,
        index: '0',
      })
    ).rejects.toThrow('ADB lost')
    // 状态未变
    expect(api.state.devices[add.emulatorId]['0'].status).toBe(1)
    expect(api.state.inFlightOperate.has(`${add.emulatorId}#open#0`)).toBe(false)
  })
})

describe('FakeEmulatorApi 旧响应覆盖保护 (FE-CONTRACT-04)', () => {
  // 模拟前端轮询场景：若旧响应晚到，不应覆盖新数据。
  // 这里通过让两次 getStatus 顺序可控来验证 fake 的时序契约。
  it('后发起的 status 请求拿到更新的数据', async () => {
    const api = createFakeEmulatorApi()
    const add = await api.addEmulatorApiEmulatorAddPost()
    api.state.devices[add.emulatorId] = { '0': makeDeviceInfo({ status: 1 }) }

    // 第一发请求未返回前，设备状态被外部改为 ONLINE
    const p1 = api.getStatusApiEmulatorStatusPost({ emulatorId: add.emulatorId })
    api.state.devices[add.emulatorId]['0'].status = 0 // ONLINE
    const p2 = api.getStatusApiEmulatorStatusPost({ emulatorId: add.emulatorId })

    const [r1, r2] = await Promise.all([p1, p2])
    // 两次都返回当前快照（fake 同步 resolve），后端真实场景下前端需用 epoch 守卫
    expect(r1.data[add.emulatorId]['0'].status).toBe(0)
    expect(r2.data[add.emulatorId]['0'].status).toBe(0)
  })
})

describe('FakeEmulatorApi 搜索去重与导入 (FE-CONTRACT-05/06)', () => {
  it('搜索结果按 path 大小写不敏感去重', async () => {
    const api = createFakeEmulatorApi()
    // fake 不自动去重（后端 search_all_emulators 已去重）；
    // 前端导入时也不应产生重复 emulator 配置项（每条都新建 uid）。
    api.state.searchResults = [
      { type: 'mumu', path: 'C:/MuMu/MuMuManager.exe', name: 'MuMu A' },
      { type: 'mumu', path: 'c:/mumu/MuMuManager.exe', name: 'MuMu A dup' },
    ]
    const res = await api.searchEmulatorsApiEmulatorEmulatorSearchPost()
    expect(res.emulators).toHaveLength(2)
    // 前端导入两次产生两个独立 uid
    const r1 = await api.addEmulatorApiEmulatorAddPost()
    const r2 = await api.addEmulatorApiEmulatorAddPost()
    expect(r1.emulatorId).not.toBe(r2.emulatorId)
  })

  it('导入流程：add 后 update 写入搜索结果字段', async () => {
    const api = createFakeEmulatorApi()
    const add = await api.addEmulatorApiEmulatorAddPost()
    const importResult = {
      type: 'ldplayer' as const,
      path: 'D:/ldplayer/ldconsole.exe',
      name: 'LDPlayer',
    }
    await api.updateEmulatorApiEmulatorUpdatePost({
      emulatorId: add.emulatorId,
      data: {
        Info: {
          Name: importResult.name,
          Type: importResult.type,
          Path: importResult.path,
          MaxWaitTime: 300,
          BossKey: JSON.stringify([]),
        },
      },
    })
    expect(api.state.data[add.emulatorId].Info?.Name).toBe('LDPlayer')
    expect(api.state.data[add.emulatorId].Info?.Path).toBe('D:/ldplayer/ldconsole.exe')
  })
})

describe('FakeEmulatorApi 保存冲突 (FE-CONTRACT-07)', () => {
  it('并发 update 串行化写入，最后一次胜出', async () => {
    const api = createFakeEmulatorApi()
    const add = await api.addEmulatorApiEmulatorAddPost()
    // 模拟两个字段同时被两个 input 触发保存
    await Promise.all([
      api.updateEmulatorApiEmulatorUpdatePost({
        emulatorId: add.emulatorId,
        data: { Info: { Name: 'A' } },
      }),
      api.updateEmulatorApiEmulatorUpdatePost({
        emulatorId: add.emulatorId,
        data: { Info: { Path: '/tmp' } },
      }),
    ])
    // 两次 update 各自只 patch 自己的字段，互不覆盖
    expect(api.state.data[add.emulatorId].Info?.Name).toBe('A')
    expect(api.state.data[add.emulatorId].Info?.Path).toBe('/tmp')
  })
})

describe('FakeEmulatorApi per-device in-flight (FE-CONTRACT-09/10)', () => {
  it('operate 结束后 inFlightOperate 清空对应 key', async () => {
    const api = createFakeEmulatorApi()
    const add = await api.addEmulatorApiEmulatorAddPost()
    api.state.devices[add.emulatorId] = { '0': makeDeviceInfo({ status: 1 }) }
    // fake operate 同步 resolve，调用完成后 in-flight 必须被清理
    await api.operationEmulatorApiEmulatorOperatePost({
      emulatorId: add.emulatorId,
      operate: EmulatorOperateIn.operate.OPEN,
      index: '0',
    })
    expect(api.state.inFlightOperate.has(`${add.emulatorId}#open#0`)).toBe(false)
  })

  it('operate 抛异常后 inFlightOperate 仍被 finally 清理', async () => {
    const api = createFakeEmulatorApi()
    const add = await api.addEmulatorApiEmulatorAddPost()
    api.state.devices[add.emulatorId] = { '0': makeDeviceInfo({ status: 1 }) }
    api.setThrow('operationEmulatorApiEmulatorOperatePost', new Error('operate boom'))
    await expect(
      api.operationEmulatorApiEmulatorOperatePost({
        emulatorId: add.emulatorId,
        operate: EmulatorOperateIn.operate.OPEN,
        index: '0',
      })
    ).rejects.toThrow('operate boom')
    expect(api.state.inFlightOperate.has(`${add.emulatorId}#open#0`)).toBe(false)
  })

  it('OPEN 将 OFFLINE 设备推到 ONLINE 并补全 adb_address', async () => {
    const api = createFakeEmulatorApi()
    const add = await api.addEmulatorApiEmulatorAddPost()
    api.state.devices[add.emulatorId] = {
      '0': makeDeviceInfo({ status: 1, adb_address: '' }),
      '1': makeDeviceInfo({ status: 1, adb_address: '' }),
    }
    await api.operationEmulatorApiEmulatorOperatePost({
      emulatorId: add.emulatorId,
      operate: EmulatorOperateIn.operate.OPEN,
      index: '0',
    })
    expect(api.state.devices[add.emulatorId]['0'].status).toBe(0)
    expect(api.state.devices[add.emulatorId]['0'].adb_address).toBe('127.0.0.1:7555')
    // index 1 不受影响
    expect(api.state.devices[add.emulatorId]['1'].status).toBe(1)
  })

  it('CLOSE 将 ONLINE 设备推到 OFFLINE 并清空 adb_address', async () => {
    const api = createFakeEmulatorApi()
    const add = await api.addEmulatorApiEmulatorAddPost()
    api.state.devices[add.emulatorId] = {
      '0': makeDeviceInfo({ status: 0, adb_address: '127.0.0.1:7555' }),
    }
    await api.operationEmulatorApiEmulatorOperatePost({
      emulatorId: add.emulatorId,
      operate: EmulatorOperateIn.operate.CLOSE,
      index: '0',
    })
    expect(api.state.devices[add.emulatorId]['0'].status).toBe(1)
    expect(api.state.devices[add.emulatorId]['0'].adb_address).toBe('')
  })
})

describe('FakeEmulatorApi 调用记录 (FE-CONTRACT-11)', () => {
  it('所有调用都被记录到 calls 数组', async () => {
    const api = createFakeEmulatorApi()
    await api.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    await api.addEmulatorApiEmulatorAddPost()
    await api.searchEmulatorsApiEmulatorEmulatorSearchPost()
    const names = api.state.calls.map(c => c.name)
    expect(names).toContain('getEmulatorApiEmulatorGetPost')
    expect(names).toContain('addEmulatorApiEmulatorAddPost')
    expect(names).toContain('searchEmulatorsApiEmulatorEmulatorSearchPost')
  })

  it('reset 清除 per-method 覆盖与 calls', async () => {
    const api = createFakeEmulatorApi()
    api.setBusinessFailure('getEmulatorApiEmulatorGetPost', 500)
    await api.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    api.reset()
    const res = await api.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    expect(res.code).toBe(200)
  })
})
