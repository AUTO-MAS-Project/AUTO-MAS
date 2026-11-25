/**
 * SignFlow 附属插件的 HTTP 端点。
 *
 * 插件路由由宿主在运行期按已启用插件挂载到 `/api/plugin/<插件名>/…`，
 * 生成客户端只在插件当时已启用时才会收录这些路径：直接重跑 `yarn openapi`
 * 会把其它没启用的插件契约模型当成过期文件删掉，生成结果不可复现。
 * 因此这里手写一层薄封装放在 services 目录，视图与 composable 只调本模块，
 * 不直接碰 fetch，也不把请求塞进 src/api。
 *
 * 信封约定：业务失败同样是 HTTP 200，靠 `code !== 200` 表达；
 * 只有网关层（插件未挂载 / 未启用到路由）才会给出 4xx。
 */
import { OpenAPI } from '@/api'

/** 插件统一信封，与后端 `OutBase` 对齐 */
export interface SignflowEnvelope {
  code: number
  status: string
  message: string
}

/**
 * 插件未启用、路由缺失或业务校验失败时抛出。
 *
 * `code` 只装后端信封里的业务码（拿不到信封时退回 HTTP 状态），
 * `httpStatus` 单独记传输层状态码，两者不再挤在一个字段里：
 * 否则 `code || response.status` 的写法会让业务码 0 被当成没给。
 */
export class SignflowError extends Error {
  readonly code: number
  readonly httpStatus: number

  constructor(message: string, code: number, httpStatus = 0) {
    super(message)
    this.name = 'SignflowError'
    this.code = code
    this.httpStatus = httpStatus
  }
}

/** 日常便笺快照：字段由宿主合同决定，插件只做一次驼峰投影 */
export interface SignflowNoteSnapshot {
  account: string
  accountUid: string
  game: string
  platform: string
  status: string
  completed: number | null
  target: number | null
  tasks: Record<string, unknown>[]
  resources: Record<string, unknown>[]
  reason: string
  updatedAt: string
  roleName: string
  roleUid: string
  server: string
  source: string
}

/** 抽卡记录，与 `signflow_gacha.models.GachaRecord` 对齐 */
export interface SignflowGachaRecord {
  game: string
  playerUid: string
  id: string
  poolType: string
  poolName: string
  name: string
  itemId: string
  itemType: string
  rarity: number
  time: string
  timezone: number
  lang: string
  isFree: boolean
  kind: string
}

/** 卡池分组摘要；`sinceTop` 是距上一个最高稀有度的抽数 */
export interface SignflowGachaPool {
  poolType: string
  poolName: string
  total: number
  topRarity: number
  topCount: number
  sinceTop: number
}

/** 单条凭据的体检结果，不含凭据原文 */
export interface SignflowTokenItem {
  field: string
  platform: string
  configured: boolean
  checked: boolean
  valid: boolean
  message: string
}

export interface SignflowTokenAccount {
  uid: string
  name: string
  enabled: boolean
  items: SignflowTokenItem[]
}

export interface SignflowTokenRefreshItem {
  field: string
  platform: string
  refreshed: boolean
  message: string
}

export interface SignflowNotesResult extends SignflowEnvelope {
  data: SignflowNoteSnapshot[]
}

export interface SignflowGachaGamesResult extends SignflowEnvelope {
  games: string[]
}

export interface SignflowGachaQueryResult extends SignflowEnvelope {
  data: SignflowGachaRecord[]
  total: number
  players: string[]
  pools: SignflowGachaPool[]
}

export interface SignflowGachaFetchResult extends SignflowEnvelope {
  added: number
  fetched: number
  warnings: string[]
}

export interface SignflowTokenStatusResult extends SignflowEnvelope {
  data: SignflowTokenAccount[]
}

export interface SignflowTokenRefreshResult extends SignflowEnvelope {
  uid: string
  items: SignflowTokenRefreshItem[]
}

export interface SignflowTokenLoginOpenResult extends SignflowEnvelope {
  sessionId: string
  captchaId: string
}

export interface SignflowTokenLoginSendResult extends SignflowEnvelope {
  sent: boolean
}

export interface SignflowTokenLoginSubmitResult extends SignflowEnvelope {
  uid: string
  field: string
}

export interface SignflowGachaQueryInput {
  game?: string
  playerUid?: string
  pool?: string
  page?: number
  pageSize?: number
}

export interface SignflowGachaFetchInput {
  game?: string
  accountUid?: string
  playerUid: string
  maxPages?: number
}

const PLUGIN_ROOT = '/api/plugin/signflow'

/** 只认对象形态的信封，避免把 HTML 错误页当成插件响应 */
const asEnvelope = (payload: unknown): SignflowEnvelope | null => {
  if (typeof payload !== 'object' || payload === null) return null
  const record = payload as Record<string, unknown>
  return typeof record.code === 'number' && typeof record.message === 'string'
    ? (record as unknown as SignflowEnvelope)
    : null
}

/**
 * 发出一次插件请求。
 *
 * 连接失败与无法解析的响应都收敛成 `SignflowError`，
 * 上层只需要读 `message` 与 `code`，不必再区分 fetch 异常与业务失败。
 */
async function request<T extends SignflowEnvelope>(path: string, body?: unknown): Promise<T> {
  const init: RequestInit =
    body === undefined
      ? { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' }
      : {
          method: 'POST',
          headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
  let response: Response
  let text: string
  try {
    response = await fetch(`${OpenAPI.BASE}${PLUGIN_ROOT}${path}`, init)
    text = await response.text()
  } catch {
    // 连接失败和读流中断都归到同一类：本地后端没起来或半路断开
    throw new SignflowError('本地服务未响应，请确认 AUTO-MAS 后端正在运行', 0)
  }
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }
  const envelope = asEnvelope(payload)
  if (!envelope) {
    throw new SignflowError(
      response.ok ? '插件返回了无法识别的响应' : `插件请求失败（HTTP ${response.status}）`,
      response.status,
      response.status
    )
  }
  if (!response.ok || envelope.code !== 200) {
    throw new SignflowError(
      envelope.message || '插件请求失败',
      envelope.code ?? response.status,
      response.status
    )
  }
  return payload as T
}

/**
 * 判断一次失败是否只是「附属插件没启用」，而不是真的出错。
 *
 * 后端三处来源，缺一不可：
 * 1. 网关没挂载路由 → HTTP 404；
 * 2. 宿主正在退出密封 → HTTP 503；
 * 3. 核心插件取不到附属能力 → HTTP 200 + 业务码 400，message 为
 *    `plugins/signflow/src/signflow/api.py` 里写死的「日常便笺插件未启用」
 *    「抽卡记录插件未启用」「Token 获取插件未启用」。
 *
 * 第 3 条目前只能认文案：插件信封没有稳定字段区分「能力缺失」与「参数有误」。
 * 文案集中在这里比对，调用方不再各自写中文子串；等插件信封补上状态位后
 * 只需改这一处。
 */
const DISABLED_SERVICE_MESSAGES = [
  '日常便笺插件未启用',
  '抽卡记录插件未启用',
  'Token 获取插件未启用',
] as const

export const isPluginUnavailable = (error: unknown): boolean => {
  if (!(error instanceof SignflowError)) return false
  if (error.httpStatus === 404 || error.httpStatus === 503) return true
  return DISABLED_SERVICE_MESSAGES.some(item => error.message.includes(item))
}

/** SignFlow 用户可见入口：查询便笺、抽卡记录、凭据体检与刷新 */
export const signflowApi = {
  /** 日常便笺；`accountIds` 为空表示全部已启用账号组 */
  queryNotes: (accountIds: string[] | null = null) =>
    request<SignflowNotesResult>('/notes/query', { accountIds }),
  /** 抽卡记录插件当前支持的游戏的标识 */
  gachaGames: () => request<SignflowGachaGamesResult>('/gacha/games'),
  /** 分页查询本地已落库的抽卡记录 */
  queryGacha: (input: SignflowGachaQueryInput = {}) =>
    request<SignflowGachaQueryResult>('/gacha/query', input),
  /** 从上游读取一次抽卡记录；只在用户点「获取记录」时调用 */
  fetchGacha: (input: SignflowGachaFetchInput) =>
    request<SignflowGachaFetchResult>('/gacha/fetch', input),
  /** 凭据体检：只回报配没配、格式对不对，不含凭据原文 */
  tokenStatus: (accountIds: string[] | null = null) =>
    request<SignflowTokenStatusResult>('/token/status', { accountIds }),
  /** 刷新可自动续期的凭据；`fields` 为空表示所有可刷新的项 */
  refreshToken: (accountUid: string, fields: string[] | null = null) =>
    request<SignflowTokenRefreshResult>('/token/refresh', { accountUid, fields }),
  /** 打开一次库街区短信登录会话，拿到会话号与极验标识 */
  openTokenLogin: (accountUid: string, phone: string) =>
    request<SignflowTokenLoginOpenResult>('/token/login/open', { accountUid, phone }),
  /** 发送短信验证码；`automatic` 需要插件侧配置云码，未配置时只会返回未发出 */
  sendTokenLoginCode: (
    sessionId: string,
    verification: Record<string, string> | null = null,
    automatic = false
  ) =>
    request<SignflowTokenLoginSendResult>('/token/login/send', {
      sessionId,
      verification,
      automatic,
    }),
  /** 提交六位短信验证码，成功后库街区凭据由后端直接落库 */
  submitTokenLoginCode: (sessionId: string, code: string) =>
    request<SignflowTokenLoginSubmitResult>('/token/login/submit', { sessionId, code }),
}
