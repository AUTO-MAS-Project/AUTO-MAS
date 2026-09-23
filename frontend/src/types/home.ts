export type HomeModuleKey =
  | 'command'
  | 'quick'
  | 'satellite'
  | 'proxy'
  | 'activities'
  | 'endfield'
  | 'starrail'
  | 'genshin'
  | 'zenless'
  | 'wutheringwaves'
  | 'nte'
  | 'reverse1999'
  | 'bluearchive'
  | 'stellasora'
  | 'arknights'

export interface HomeLayoutConfig {
  moduleOrder: HomeModuleKey[]
  hiddenModules: HomeModuleKey[]
  hideScrollHint?: boolean
  /** 活动轮播是否自动播放；未设置按开启处理 */
  carouselAutoplay?: boolean
  /** 首页轮播下方是否显示当前游戏的日常便笺；由游戏社区设置里的总开关控制，默认关闭 */
  activityNotesVisible?: boolean
  /** 首页便笺被单独关闭的游戏；在「编辑布局」里控制 */
  hiddenActivityNotes?: HomeModuleKey[]
}

export interface HomeModuleDescriptor {
  key: HomeModuleKey
  title: string
  visible: boolean
}

interface ActivityInfo {
  Tip: string
  StageName: string
  UtcStartTime: string
  UtcExpireTime: string
  TimeZone: number
}

export interface ActivityItem {
  Display: string
  Value: string
  Drop: string
  DropName: string
  Activity: ActivityInfo
}

export interface ResourceItem {
  Display: string
  Value: string
  Drop: string
  DropName: string
  Activity: Pick<ActivityInfo, 'Tip' | 'StageName'>
}

interface StageOption {
  label: string
  value: string | null
}

interface StageOverview {
  Activity: ActivityItem[]
  Resource: ResourceItem[]
  Options: StageOption[]
}

export interface ProxyInfo {
  LastProxyDate: string
  ProxyTimes: number
  ErrorTimes: number
  ErrorInfo: Record<string, unknown>
}

interface EndfieldActivityItem {
  Id: string
  Name: string
  StartTime: string
  EndTime: string
  ImageUrl: string
  Tags: string[]
}

interface EndfieldPoolItem {
  Id: string
  Name: string
  Type: string
  StartTime: string
  EndTime: string
  ImageUrl: string
  UpCharacters: string[]
}

export interface EndfieldActivityOverview {
  Available: boolean
  Stale: boolean
  Message: string
  Version: string
  UpdatedAt: string
  SourceName: string
  SourceUrl: string
  Pools: EndfieldPoolItem[]
  Activities: EndfieldActivityItem[]
}

export const createEmptyEndfieldActivityOverview = (): EndfieldActivityOverview => ({
  Available: false,
  Stale: false,
  Message: '',
  Version: '',
  UpdatedAt: '',
  SourceName: 'AKEData',
  SourceUrl: 'https://www.akedata.wiki',
  Pools: [],
  Activities: [],
})

export interface SraActivityItem {
  name: string
  description: string
  startTime: string
  endTime: string
  cover?: string
}

export interface SraActivityOverview {
  Available: boolean
  Stale: boolean
  Message: string
  version: string
  versionName: string
  cover?: string
  startTime: string
  endTime: string
  activities: SraActivityItem[]
}

export type Reverse1999ActivityOverview = SraActivityOverview
export type BlueArchiveActivityOverview = SraActivityOverview

/**
 * 星塔旅人的活动数据：后端原样转发 StellaBase 的响应，站点已经按状态分好三组，
 * 前端自己挑进行中的那条。与其它游戏不同，这里不需要版本维度，所以单独定义。
 */
export interface StellaActivityItem {
  title?: string
  startTime?: string
  endTime?: string
  /**
   * 活动配图，站点给三张相对路径：
   * ``background`` 1644×900（弹窗大图，拿来做封面）、``banner`` 310×138、
   * ``tabBackground`` 308×160（后两张太小，轮播会按「小图嵌入」处理成一小块）。
   */
  textures?: { background?: string; banner?: string; tabBackground?: string }
}

/** 国服官网主推横幅：官方活动主视觉 + 对应新闻页 + 官方标题（前几条才有） */
export interface StellaOfficialBanner {
  banner?: string
  url?: string
  title?: string
  /** 标题与当前活动名对得上：封面优先用它，没有命中才退到最新一条 */
  matched?: boolean
}

export interface StellaActivityOverview {
  current: StellaActivityItem[]
  upcoming: StellaActivityItem[]
  ended: StellaActivityItem[]
  /** 国服官网的主推横幅，取不到时为空数组（活动大图 404 时拿它兜底） */
  official: StellaOfficialBanner[]
  /**
   * 这次是否成功取到了活动排期。
   *
   * 与「当前有没有进行中的活动」是两件事：站点正常返回、只是两组都空，也算取到了，
   * 卡片据此显示「暂无进行中的活动」而不是「数据不可用」。
   */
  Available: boolean
}

export const createEmptyStellaActivityOverview = (): StellaActivityOverview => ({
  current: [],
  upcoming: [],
  ended: [],
  official: [],
  Available: false,
})

/** 碧蓝档案的三个服务器；与数据源的 line_type 一一对应 */
export type BlueArchiveServerKey = 'jp' | 'global' | 'cn'

/**
 * 单张碧蓝档案卡片要同时承载三个服的数据：数据源按服各拉一次，
 * 卡片内用分段控件切换展示，任一服失败只影响它自己。
 */
export interface BlueArchiveServerOverview {
  key: BlueArchiveServerKey
  /** 已按当前界面语言本地化的服名（日服 / 国际服 / 国服），直接用作切换控件文案 */
  label: string
  overview: BlueArchiveActivityOverview
}

export const createEmptySraActivityOverview = (message = ''): SraActivityOverview => ({
  Available: false,
  Stale: false,
  Message: message,
  version: '',
  versionName: '',
  cover: '',
  startTime: '',
  endTime: '',
  activities: [],
})

export interface HomeOverviewResponse {
  Stage: StageOverview
  StageByServer: Record<string, StageOverview>
  Proxy: Record<string, ProxyInfo>
}

/** 首页活动轮播里单张 banner 的统一形状，屏蔽各游戏数据源的差异 */
export interface ActivityBannerItem {
  key: HomeModuleKey
  /** 游戏短名，用于 banner 标题与切换条 */
  title: string
  /** 主题色，无封面时用来生成底纹 */
  accent: string
  /** 封面图地址，取不到时为空串 */
  cover: string
  /**
   * 主封面加载失败时依次尝试的备用图（星塔旅人的活动大图时有时无：
   * StellaBase 的 `background` 常 404，官网横幅与站点小图依次补位）。
   */
  coverCandidates?: string[]
  /** 版本名或当期活动名 */
  subtitle: string
  /** 活动开始时间；用来区分「还没开始」与「进行中」，取不到时为空串 */
  startTime: string
  /** 倒计时终点，取不到时为空串 */
  endTime: string
  loading: boolean
  available: boolean
  stale: boolean
  /**
   * 这张卡展示的是「刚结束的那场」而不是进行中的活动。
   *
   * 与碧蓝档案同口径：没有进行中的活动时退回最近结束的一场，倒计时自然显示
   * 「[活动已结束]」，再补一句「后续活动即将开始」。
   */
  ended?: boolean
}
