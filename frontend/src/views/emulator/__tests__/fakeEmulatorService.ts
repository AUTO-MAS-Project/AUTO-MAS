/**
 * Fake Emulator Service for backend contract matrix tests.
 *
 * 模拟 `app/plugins/emulator_compat.py` 的 `LegacyEmulatorService` 与
 * 可选 plugin provider 的对外契约，使前端测试可以在不启动真实后端的
 * 情况下验证 host fallback / real provider / 失败恢复 / 未知 provider /
 * 超时 / 取消 等场景。
 *
 * 本文件只描述契约形状，不导入 Python 后端代码；测试通过 vi.mock
 * 注入到 `@/api` 的 Service 即可。
 *
 * 与后端 `LegacyEmulatorService` 字段保持一致：
 *  - get_config(emulator_id) -> (index, data)
 *  - add() -> (uid, config)
 *  - update(emulator_id, data)
 *  - delete(emulator_id)
 *  - reorder(index_list)
 *  - operate(operate, emulator_id, index)
 *  - status(emulator_id) -> dict
 *  - search_installed() -> list[dict]
 *  - list_options() / list_device_options(emulator_id)
 *  - get_instance(emulator_id) -> DeviceBase-like
 */
import type {
  EmulatorConfig,
  EmulatorConfigIndexItem,
  EmulatorSearchResult,
  DeviceInfo,
} from '@/api'
import { EmulatorOperateIn } from '@/api'

export type ProviderKind = 'host' | 'plugin' | 'unknown'

export interface FakeProviderConfig {
  kind: ProviderKind
  /** 当 kind === 'plugin' 且 installed=true 时，get_emulator_service 返回 plugin provider */
  installed: boolean
  /** plugin provider 抛出的错误；undefined 表示不抛 */
  pluginError?: Error
  /** operate 调用延迟（ms），用于超时测试；由 fake timers 推进 */
  operateDelayMs?: number
  /** operate 是否支持取消（AbortSignal 风格，这里简化为 flag） */
  cancellable?: boolean
}

export interface FakeEmulatorServiceState {
  provider: FakeProviderConfig
  index: EmulatorConfigIndexItem[]
  data: Record<string, EmulatorConfig>
  devices: Record<string, Record<string, DeviceInfo>>
  searchResults: EmulatorSearchResult[]
  /** 操作日志，用于断言 host fallback 与 plugin 路径 */
  operationLog: Array<{ via: ProviderKind; op: string; emulatorId: string; index: string }>
  /** 已取消的 operate key 集合 */
  cancelled: Set<string>
  nextUid: number
}

export function createFakeEmulatorServiceState(
  provider: FakeProviderConfig = { kind: 'host', installed: false }
): FakeEmulatorServiceState {
  return {
    provider,
    index: [],
    data: {},
    devices: {},
    searchResults: [],
    operationLog: [],
    cancelled: new Set(),
    nextUid: 0,
  }
}

export interface FakeEmulatorService {
  state: FakeEmulatorServiceState
  get_config(emulatorId: string | null): Promise<{
    index: EmulatorConfigIndexItem[]
    data: Record<string, EmulatorConfig>
  }>
  add(): Promise<{ uid: string; config: EmulatorConfig }>
  update(emulatorId: string, data: unknown): Promise<void>
  delete(emulatorId: string): Promise<void>
  reorder(indexList: string[]): Promise<void>
  operate(operate: string, emulatorId: string, index: string): Promise<void>
  status(emulatorId: string | null): Promise<Record<string, Record<string, DeviceInfo>>>
  search_installed(): Promise<EmulatorSearchResult[]>
  list_options(): Promise<{ value: string; label: string }[]>
  list_device_options(emulatorId: string): Promise<{ value: string; label: string }[]>
  /** 测试夹具：标记某次 operate 被取消 */
  markCancelled(emulatorId: string, op: string, index: string): void
}

/**
 * 创建 fake service。`providerOverride` 可在测试中动态切换以模拟 host fallback。
 */
export function createFakeEmulatorService(
  state: FakeEmulatorServiceState = createFakeEmulatorServiceState()
): FakeEmulatorService {
  const resolveVia = (): ProviderKind => {
    if (state.provider.kind === 'plugin' && state.provider.installed) {
      return 'plugin'
    }
    // unknown 与 host 缺失都退回 host fallback
    return 'host'
  }

  const ensurePluginOrThrow = () => {
    if (state.provider.kind === 'plugin' && !state.provider.installed) {
      throw state.provider.pluginError ?? new Error('plugin not installed')
    }
    if (state.provider.kind === 'unknown') {
      throw new Error('unknown provider kind')
    }
  }

  const svc: FakeEmulatorService = {
    state,
    async get_config(emulatorId) {
      ensurePluginOrThrow()
      if (emulatorId) {
        const item = state.index.find(i => i.uid === emulatorId)
        const data: Record<string, EmulatorConfig> = {}
        if (item && state.data[emulatorId]) data[emulatorId] = state.data[emulatorId]
        return { index: item ? [item] : [], data }
      }
      return { index: [...state.index], data: { ...state.data } }
    },
    async add() {
      ensurePluginOrThrow()
      const uid = `emu-${String(state.nextUid++).padStart(4, '0')}`
      const config: EmulatorConfig = {
        Info: {
          Name: '未命名',
          Type: 'general',
          Path: '',
          MaxWaitTime: 300,
          BossKey: '[]',
          ForceKillOnClose: false,
        },
      } as EmulatorConfig
      state.index.push({ uid, type: 'general' } as EmulatorConfigIndexItem)
      state.data[uid] = config
      return { uid, config }
    },
    async update(emulatorId, data) {
      ensurePluginOrThrow()
      const target = state.data[emulatorId]
      if (!target) throw new Error(`emulator ${emulatorId} not found`)
      const patch = (data as { Info?: Record<string, unknown> })?.Info
      if (patch) target.Info = { ...target.Info, ...patch } as EmulatorConfig['Info']
    },
    async delete(emulatorId) {
      ensurePluginOrThrow()
      const idx = state.index.findIndex(i => i.uid === emulatorId)
      if (idx === -1) throw new Error(`emulator ${emulatorId} not found`)
      state.index.splice(idx, 1)
      delete state.data[emulatorId]
      delete state.devices[emulatorId]
    },
    async reorder(indexList) {
      ensurePluginOrThrow()
      const map = new Map(state.index.map(i => [i.uid, i]))
      state.index = indexList
        .map(uid => map.get(uid))
        .filter((x): x is EmulatorConfigIndexItem => !!x)
    },
    async operate(operate, emulatorId, index) {
      ensurePluginOrThrow()
      const via = resolveVia()
      state.operationLog.push({ via, op: operate, emulatorId, index })
      if (state.provider.operateDelayMs && state.provider.operateDelayMs > 0) {
        // 由测试用 fake timers 推进；这里 await 一个永不 resolve 的 Promise
        // 直到测试主动 markCancelled 或 timers 推进足够时间。
        await new Promise<void>(resolve => {
          setTimeout(resolve, state.provider.operateDelayMs)
        })
      }
      const devices = state.devices[emulatorId] ?? {}
      const cur = devices[index]
      if (operate === EmulatorOperateIn.operate.OPEN && cur) {
        cur.status = 0
        cur.adb_address = `127.0.0.1:${7555 + Number(index)}`
      } else if (operate === EmulatorOperateIn.operate.CLOSE && cur) {
        cur.status = 1
        cur.adb_address = ''
      }
    },
    async status(emulatorId) {
      ensurePluginOrThrow()
      const out: Record<string, Record<string, DeviceInfo>> = {}
      const targets = emulatorId ? [emulatorId] : state.index.map(i => i.uid)
      for (const uid of targets) {
        if (state.devices[uid]) out[uid] = { ...state.devices[uid] }
      }
      return out
    },
    async search_installed() {
      ensurePluginOrThrow()
      return [...state.searchResults]
    },
    async list_options() {
      ensurePluginOrThrow()
      return state.index.map(i => ({
        value: i.uid,
        label: state.data[i.uid]?.Info?.Name ?? i.uid,
      }))
    },
    async list_device_options(emulatorId) {
      ensurePluginOrThrow()
      const devs = state.devices[emulatorId] ?? {}
      return Object.entries(devs).map(([idx, d]) => ({
        value: idx,
        label: d.title ?? idx,
      }))
    },
    markCancelled(emulatorId, op, index) {
      state.cancelled.add(`${emulatorId}#${op}#${index}`)
    },
  }
  return svc
}
