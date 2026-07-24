/**
 * Fake Emulator API service for deterministic Vitest tests.
 *
 * Subagent C 专用测试夹具：在不依赖 Subagent B 实装、不启动真实后端、
 * 也不修改 `frontend/src/api/**` 的前提下，提供与生成 Service 形状一致的
 * 可控 stub，用于 Emulator 专区契约测试和 characterization 测试基线。
 *
 * 设计原则：
 *  - 仅返回 OpenAPI 已声明的形状（参考 src/api/models/Emulator*.ts）。
 *  - 所有副作用通过 `calls` 数组暴露，便于断言。
 *  - 通过 `setResponse`、`setThrow` 控制下一次调用的结果，覆盖成功 /
 *    业务失败（code !== 200）/ 抛异常三种路径。
 *  - 不引入固定 sleep，所有时序由测试用 fake timers 控制。
 */
import type {
  EmulatorConfig,
  EmulatorConfigIndexItem,
  EmulatorGetIn,
  EmulatorGetOut,
  EmulatorCreateOut,
  EmulatorUpdateIn,
  EmulatorDeleteIn,
  EmulatorStatusOut,
  EmulatorSearchOut,
  EmulatorSearchResult,
  DeviceInfo,
} from '@/api'
import { EmulatorOperateIn } from '@/api'

export interface FakeEmulatorApiCall {
  name: string
  args: unknown
  ts: number
}

export interface FakeEmulatorApiState {
  index: EmulatorConfigIndexItem[]
  data: Record<string, EmulatorConfig>
  devices: Record<string, Record<string, DeviceInfo>>
  searchResults: EmulatorSearchResult[]
  nextUid: number
  /** 业务失败时返回的 code，200 表示成功 */
  forcedCode: number
  forcedMessage: string
  /** 抛出异常时的 Error，undefined 表示不抛 */
  thrownError: Error | undefined
  /** 控制接口级覆盖：key=方法名，value={code, message, error} */
  perMethod: Record<string, { code?: number; message?: string; error?: Error }>
  calls: FakeEmulatorApiCall[]
  /** operate 的 in-flight 队列，用于测试 per-device 防重入 */
  inFlightOperate: Set<string>
}

export function makeEmulatorConfig(overrides: Partial<EmulatorConfig> = {}): EmulatorConfig {
  return {
    Info: {
      Name: '未命名',
      Type: 'general',
      Path: '',
      MaxWaitTime: 300,
      BossKey: '[]',
      ForceKillOnClose: false,
      ...(overrides.Info ?? {}),
    },
  } as EmulatorConfig
}

export function makeIndexItem(uid: string, type: string = 'general'): EmulatorConfigIndexItem {
  return { uid, type } as EmulatorConfigIndexItem
}

export function makeDeviceInfo(overrides: Partial<DeviceInfo> = {}): DeviceInfo {
  return {
    title: 'device-0',
    status: 1, // OFFLINE
    adb_address: '',
    ...overrides,
  } as DeviceInfo
}

export function createFakeEmulatorApiState(): FakeEmulatorApiState {
  return {
    index: [],
    data: {},
    devices: {},
    searchResults: [],
    nextUid: 0,
    forcedCode: 200,
    forcedMessage: '',
    thrownError: undefined,
    perMethod: {},
    calls: [],
    inFlightOperate: new Set(),
  }
}

function recordCall(state: FakeEmulatorApiState, name: string, args: unknown) {
  state.calls.push({ name, args, ts: Date.now() })
}

function resolveOutcome<T>(state: FakeEmulatorApiState, method: string, success: () => T): T {
  recordCall(state, method, success.toString())
  const override = state.perMethod[method]
  if (override?.error) {
    throw override.error
  }
  if (override?.code !== undefined && override.code !== 200) {
    return {
      code: override.code,
      status: 'error',
      message: override.message ?? `${method} forced failure`,
    } as unknown as T
  }
  if (state.thrownError) {
    const err = state.thrownError
    state.thrownError = undefined
    throw err
  }
  return success()
}

export interface FakeEmulatorApi {
  state: FakeEmulatorApiState
  getEmulatorApiEmulatorGetPost: (req: EmulatorGetIn) => Promise<EmulatorGetOut>
  addEmulatorApiEmulatorAddPost: () => Promise<EmulatorCreateOut>
  updateEmulatorApiEmulatorUpdatePost: (
    req: EmulatorUpdateIn
  ) => Promise<{ code: number; status: string; message?: string }>
  deleteEmulatorApiEmulatorDeletePost: (
    req: EmulatorDeleteIn
  ) => Promise<{ code: number; status: string; message?: string }>
  operationEmulatorApiEmulatorOperatePost: (
    req: EmulatorOperateIn
  ) => Promise<{ code: number; status: string; message?: string }>
  getStatusApiEmulatorStatusPost: (req: EmulatorGetIn) => Promise<EmulatorStatusOut>
  searchEmulatorsApiEmulatorEmulatorSearchPost: () => Promise<EmulatorSearchOut>
  /** 测试夹具：注入业务失败（非 200） */
  setBusinessFailure: (method: string, code: number, message?: string) => void
  /** 测试夹具：注入抛异常 */
  setThrow: (method: string, error: Error) => void
  /** 测试夹具：清除所有覆盖 */
  reset: () => void
}

export function createFakeEmulatorApi(
  state: FakeEmulatorApiState = createFakeEmulatorApiState()
): FakeEmulatorApi {
  const api: FakeEmulatorApi = {
    state,
    async getEmulatorApiEmulatorGetPost(req: EmulatorGetIn) {
      return resolveOutcome(state, 'getEmulatorApiEmulatorGetPost', () => {
        if (req.emulatorId) {
          const item = state.index.find(i => i.uid === req.emulatorId)
          const data: Record<string, EmulatorConfig> = {}
          if (item && state.data[req.emulatorId!]) {
            data[req.emulatorId!] = state.data[req.emulatorId!]
          }
          return {
            code: 200,
            status: 'ok',
            message: '',
            index: item ? [item] : [],
            data,
          } as EmulatorGetOut
        }
        return {
          code: 200,
          status: 'ok',
          message: '',
          index: [...state.index],
          data: { ...state.data },
        } as EmulatorGetOut
      })
    },
    async addEmulatorApiEmulatorAddPost() {
      return resolveOutcome(state, 'addEmulatorApiEmulatorAddPost', () => {
        const uid = `emu-${String(state.nextUid++).padStart(4, '0')}`
        const cfg = makeEmulatorConfig()
        state.index.push(makeIndexItem(uid))
        state.data[uid] = cfg
        return {
          code: 200,
          status: 'ok',
          message: '',
          emulatorId: uid,
          data: cfg,
        } as EmulatorCreateOut
      })
    },
    async updateEmulatorApiEmulatorUpdatePost(req: EmulatorUpdateIn) {
      return resolveOutcome(state, 'updateEmulatorApiEmulatorUpdatePost', () => {
        const target = state.data[req.emulatorId]
        if (!target) {
          return {
            code: 404,
            status: 'error',
            message: `emulator ${req.emulatorId} not found`,
          }
        }
        const patch = (req.data as unknown as { Info?: Record<string, unknown> })?.Info
        if (patch) {
          target.Info = { ...target.Info, ...patch } as EmulatorConfig['Info']
        }
        return { code: 200, status: 'ok', message: '' }
      })
    },
    async deleteEmulatorApiEmulatorDeletePost(req: EmulatorDeleteIn) {
      return resolveOutcome(state, 'deleteEmulatorApiEmulatorDeletePost', () => {
        const idx = state.index.findIndex(i => i.uid === req.emulatorId)
        if (idx === -1) {
          return {
            code: 404,
            status: 'error',
            message: `emulator ${req.emulatorId} not found`,
          }
        }
        state.index.splice(idx, 1)
        delete state.data[req.emulatorId]
        delete state.devices[req.emulatorId]
        return { code: 200, status: 'ok', message: '' }
      })
    },
    async operationEmulatorApiEmulatorOperatePost(req: EmulatorOperateIn) {
      const key = `${req.emulatorId}#${req.operate}#${req.index}`
      state.inFlightOperate.add(key)
      try {
        return await resolveOutcome(state, 'operationEmulatorApiEmulatorOperatePost', () => {
          // 模拟状态变迁：open -> ONLINE；close -> OFFLINE
          // 真实后端走 task 异步推进 STARTING/CLOSING，这里只在调用返回后
          // 设终态以便轮询测试观察。中间态由测试通过 setDeviceStatus 注入。
          const devices = state.devices[req.emulatorId] ?? {}
          const cur = devices[req.index]
          if (req.operate === EmulatorOperateIn.operate.OPEN) {
            if (cur) {
              cur.status = 0 // ONLINE
              cur.adb_address = `127.0.0.1:${7555 + Number(req.index)}`
            }
          } else if (req.operate === EmulatorOperateIn.operate.CLOSE) {
            if (cur) {
              cur.status = 1 // OFFLINE
              cur.adb_address = ''
            }
          }
          // SHOW 不改变状态
          return { code: 200, status: 'ok', message: 'ok' }
        })
      } finally {
        state.inFlightOperate.delete(key)
      }
    },
    async getStatusApiEmulatorStatusPost(req: EmulatorGetIn) {
      return resolveOutcome(state, 'getStatusApiEmulatorStatusPost', () => {
        const out: Record<string, Record<string, DeviceInfo>> = {}
        const targets = req.emulatorId ? [req.emulatorId] : state.index.map(i => i.uid)
        for (const uid of targets) {
          if (state.devices[uid]) {
            out[uid] = { ...state.devices[uid] }
          }
        }
        return {
          code: 200,
          status: 'ok',
          message: '',
          data: out,
        } as EmulatorStatusOut
      })
    },
    async searchEmulatorsApiEmulatorEmulatorSearchPost() {
      return resolveOutcome(state, 'searchEmulatorsApiEmulatorEmulatorSearchPost', () => {
        return {
          code: 200,
          status: 'ok',
          message: '',
          emulators: [...state.searchResults],
        } as EmulatorSearchOut
      })
    },
    setBusinessFailure(method, code, message) {
      state.perMethod[method] = { code, message }
    },
    setThrow(method, error) {
      state.perMethod[method] = { error }
    },
    reset() {
      state.perMethod = {}
      state.thrownError = undefined
      state.forcedCode = 200
      state.forcedMessage = ''
      state.calls.length = 0
      state.inFlightOperate.clear()
    },
  }
  return api
}

/**
 * 安装/还原 fake Service 到全局，用于 characterization 测试。
 * 测试需自行管理 vi.mock 与还原。
 */
export function installFakeService(_api: FakeEmulatorApi): () => void {
  // 占位：实际注入由测试通过 vi.mock('@/api') 完成。
  // 这里只提供签名以便后续 B 实装时复用。
  return () => {
    /* noop */
  }
}
