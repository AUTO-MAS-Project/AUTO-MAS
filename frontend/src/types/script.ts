// 脚本类型定义
import type {
  HSRConfig,
  HSRConfig_TaskMapping,
  MaaConfig,
  GeneralConfig,
  OkwwConfig,
  OkNteConfig,
  SrcConfig,
  MaaEndConfig,
  BetterGIConfig,
  ZzzOdConfig,
  BAAHConfig,
} from '@/api'
import type {
  AutoEssenceLocation,
  AutoEssenceMenu,
  MaaEndAutoCollectMode,
  MaaEndDeliveryCommissionSource,
  MaaEndTaskSwitch,
  ProtocolSpaceTaskValue,
  RewardSetOption,
  SanityTaskType,
} from '@/utils/maaEndProtocolSpace'

export type ScriptType =
  | 'MAA'
  | 'General'
  | 'Okww'
  | 'OkNte'
  | 'SRC'
  | 'MaaEnd'
  | 'M9A'
  | 'MaaFW'
  | 'HSR'
  | 'BetterGI'
  | 'ZzzOd'
  | 'BAAH'

// MAA脚本配置
export interface MAAScriptConfig {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    TaskTransitionMethod: string
    ProxyTimesLimit: number
    ADBSearchRange: number
    RunTimesLimit: number
    AnnihilationTimeLimit: number
    RoutineTimeLimit: number
    IfCheckGameUpdate: boolean
    IfAutoInstallGameApk: boolean
    GameUpdateTimeLimit: number
  }
  Emulator: {
    Id: string
    Index: string
  }
  SubConfigsInfo: {
    UserData: {
      instances: unknown[]
    }
  }
}

// 通用脚本配置
export interface GeneralScriptConfig {
  Game: {
    Arguments: string
    Enabled: boolean
    IfForceClose: boolean
    Path: string
    Type: string
    WaitTime: number
    EmulatorId: string
    EmulatorIndex: string
    URL: string
    ProcessName: string
  }
  Info: {
    Name: string
    RootPath: string
  }
  Run: {
    ProxyTimesLimit: number
    RunTimeLimit: number
    RunTimesLimit: number
  }
  Script: {
    Arguments: string
    ConfigPath: string
    ConfigPathMode: string
    ErrorLog: string
    IfTrackProcess: boolean
    TrackProcessName: string
    TrackProcessExe: string
    TrackProcessCmdline: string
    LogPath: string
    LogPathFormat: string
    LogTimeEnd: number
    LogTimeStart: number
    LogTimeFormat: string
    LogHookEnabled: boolean
    LogHookRules: string
    PushLogEnabled: boolean
    PushLogPatterns: string
    ScriptPath: string
    SuccessLog: string
    SuccessLogMode: string
    ErrorLogMode: string
    UpdateConfigMode: string
  }
  SubConfigsInfo: {
    UserData: {
      instances: unknown[]
    }
  }
}

// SRC脚本配置
export interface SRCScriptConfig {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    TaskTransitionMethod: string
    ProxyTimesLimit: number
    RunTimesLimit: number
    RunTimeLimit: number
    IfCheckGameUpdate: boolean
    IfAutoInstallGameApk: boolean
    GameUpdateTimeLimit: number
  }
  Emulator: {
    Id: string
    Index: string
  }
}

type MaaEndTaskSwitchConfig = Record<`If${MaaEndTaskSwitch}`, boolean> & {
  IfSeizeDeliveryJobs: boolean
}

export type MaaEndTaskConfig = MaaEndTaskSwitchConfig & {
  IfAutoCollect: boolean
  SeizeDeliveryJobsReward: number
  SeizeDeliveryJobsCommissionSource: MaaEndDeliveryCommissionSource
  AutoCollectMode: MaaEndAutoCollectMode
  AutoCollectRoutes: string[] | null
  AutoCollectCommonRoutes: string[] | null
  SanityTaskType: SanityTaskType
  OperatorProgression: ProtocolSpaceTaskValue
  WeaponProgression: ProtocolSpaceTaskValue
  CrisisDrills: ProtocolSpaceTaskValue
  RewardsSetOption: RewardSetOption
  AutoEssenceSpecifiedLocation: AutoEssenceLocation
  AutoEssenceMenu: AutoEssenceMenu
  AutoEssenceTargetWeapons: string[]
}

// MaaEnd脚本配置
export interface MaaEndScriptConfig {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    RunTimeLimit: number
    ProxyTimesLimit: number
    RunTimesLimit: number
    AccountSwitchMethod: 'MAS' | 'MAAEND'
    TaskTransitionMethod: 'NoAction' | 'ExitGame'
  }
  Game: {
    ControllerType: string | null
    Path: string
    Arguments: string
    WaitTime: number
    EmulatorId: string
    EmulatorIndex: string
    SetResolution: boolean
    CloseOnFinish: boolean
    RestoreDisplayType: 'Window' | 'Fullscreen'
    RestoreResolution: 'Off' | 'Original' | '1920x1080' | '2560x1440' | '3840x2160' | 'Custom'
    RestoreResolutionWidth: number
    RestoreResolutionHeight: number
  }
}

// M9A 是 MaaFW 引擎的特调类型：配置模型与 MaaFW 同形（后端 M9AConfig 是 MaaFWConfig 的同形子类），
// 页面与类型都直接复用 MaaFW 的；这里只留一个别名，方便按名字找到它。
export type M9AScriptConfig = MaaFWScriptConfig

// HSR 脚本配置（后端已通过 HSRConfig OpenAPI 暴露类型）
export type HSRScriptConfig = HSRConfig

// MaaFramework 项目脚本配置（宿主 Config v1；托管字段仍保留兼容读取）
export type MaaFWLaunchMode = 'DirectExe' | 'AttachOnly'
/** 启动 Unity 游戏前临时改成的窗口分辨率；Off 不修改。 */
export type MaaFWUnityResolution = 'Off' | '1920x1080' | '1280x720'

/** MaaFW 项目自动更新时机；解析与兼容映射见 composables/useMaaFWProjectUpdate.ts。 */
export type MaaFWAutoUpdateMode = 'Off' | 'BeforeRun' | 'AfterRun'

export interface MaaFWScriptConfig {
  Info: {
    Name: string
    ProjectLabel?: string
    Path: string
    Controller: string
    Resource: string
  }
  Emulator: {
    Id: string
    Index: string
  }
  Device: {
    AdbPath: string
    AdbAddress: string
    AdbScreencapMethods: number
    AdbInputMethods: number
    HWnd: number
    Win32ScreencapMethod: number
    Win32MouseMethod: number
    Win32KeyboardMethod: number
    GamepadType: number
    PlayCoverAddress: string
    PlayCoverUuid: string
  }
  Game: {
    /** DirectExe：MAS 启动并在结束后关闭（默认）；AttachOnly：其他方式启停，MAS 只接管。 */
    LaunchMode: MaaFWLaunchMode
    LaunchPath: string
    /** 安卓游戏包名，留空则从项目的 pipeline 中自动识别。 */
    PackageName: string
    Arguments: string
    WaitTime: number
    /** 由 MAS 启动游戏时，窗口出现后至少再等多少秒才下发第一个任务；0 关闭。 */
    /** DirectExe 下启动前按 exe 反查 Unity 注册表，临时改成所选窗口尺寸，关闭后恢复。 */
    UnityResolution: MaaFWUnityResolution
  }
  Update: {
    /** 自动更新时机：不更新 / 运行前 / 运行后。 */
    AutoUpdateMode: MaaFWAutoUpdateMode
    /** 更新包的下载源，由用户显式选择，没有「自动」；默认 GitHub（零配置可用）。 */
    Source: 'MirrorChyan' | 'GitHub'
    /** 更新通道：稳定版 / 测试版，默认稳定版；不跟随全局，也不开放 alpha。 */
    Channel: 'stable' | 'beta'
    /** 脚本自己的 Mirror 酱 CDK，选 Mirror 酱作为更新源时必填；不从全局设置兜底。 */
    MirrorChyanCDK: string
    /**
     * 只对这个项目生效的网络代理，`host:port` 或带协议；更新包下载与运行环境安装走它。
     * 留空跟随全局（设置 → 其他 → 网络代理），兜底在后端合并，前端不做预填。
     */
    ProxyAddress: string
    /**
     * @deprecated 后端已改用 AutoUpdateMode；旧配置可能只有这个字段，仅供读取时映射，
     * 前端不再写入。见 useMaaFWProjectUpdate.resolveAutoUpdateMode。
     */
    IfAutoUpdate?: boolean
  }
  /**
   * 内嵌副本：运行、预览、更新都在 AUTO-MAS 自己投影出的瘦副本上，没有开关。
   * 副本路径由脚本 ID 推出，不在这里、也不可手改；`Info.Path` 只是用户选的来源目录。
   */
  Embedded: {
    /** 导入时来源的 interface 版本，仅展示。 */
    SourceVersion: string
    /** 导入时间，仅展示。 */
    ImportedAt: string
    /** 投影报告 JSON 文本；结构见 MaaFWEmbeddedProjection。 */
    Report: string
  }
  Run: {
    ProxyTimesLimit: number
    RunTimesLimit: number
    RunTimeLimit: number
    DailyOnceTasks: string | string[]
    WeeklyOnceTasks: string | string[]
    MonthlyOnceTasks: string | string[]
  }
  /**
   * 阶段性保留：manager.py 仍从 Selection.* 读取运行范围。
   * 回收版前端写入 Info.* / 用户任务配置，此字段仅用于兼容旧简版脚本编辑页读取。
   */
  Selection?: {
    Controller?: string | string[] | null
    Resource?: string | string[] | null
    Tasks?: string | string[] | null
  }
}

export type MaaFWTaskOptionValue = string | string[] | Record<string, string>

/**
 * 三个字段的 key 都是「任务实例 id」而不是任务名：同一个任务可以被重复加入队列，
 * 首份的 id 就是裸任务名，第二份起是 `<任务名>__MAS_DUP__<随机后缀>`。
 */
export interface MaaFWTaskSnapshot {
  taskOrder: string[]
  taskChecked: Record<string, boolean>
  taskOptions: Record<string, Record<string, MaaFWTaskOptionValue>>
}

/** 任务队列里的一项：同名任务可以有多份，靠 `id` 区分。 */
export interface MaaFWQueuedTaskItem {
  id: string
  task: MaaFWTaskInfo
  /** 同名副本中的序号，从 1 起；仅在 `copyTotal > 1` 时需要显示 */
  copyIndex: number
  copyTotal: number
}

export interface MaaFWUserConfig {
  Info: {
    Name: string
    Status: boolean
    RemainedDay: number
    IfScriptBeforeTask: boolean
    ScriptBeforeTask: string
    IfScriptAfterTask: boolean
    ScriptAfterTask: string
    Notes: string
    Tag?: string | null
    Account: string
    Password: string
    Resource?: string
    Mode?: '脚本' | '用户' | '直控'
    /** 快速配置：独立于配置来源的用户级开关 */
    IfQuickConfig?: boolean
  }
  Task: {
    SelectedPreset: string
    TaskSnapshot: string | MaaFWTaskSnapshot
  }
  Notify: {
    Enabled: boolean
    IfSendStatistic: boolean
    IfSendMail: boolean
    ToAddress: string
    IfServerChan: boolean
    ServerChanKey: string
  }
  Data: {
    LastProxyDate: string
    ProxyTimes: number
    IfPassCheck: boolean
    LastProxyStatus: string
    PeriodTaskRecords: string | Record<string, Record<string, string>>
  }
}

export interface MaaFWProjectInfo {
  name: string
  label?: string | null
  title?: string | null
  version?: string | null
  github?: string | null
  mirrorchyanRid?: string | null
  mirrorchyanMultiplatform?: boolean | null
  description?: string | null
  icon?: string | null
}

const MAAFW_SUPPORTED_CONTROLLER_TYPES = ['Adb', 'Win32', 'Gamepad', 'PlayCover'] as const

export const isSupportedMaaFWControllerType = (type: string) =>
  (MAAFW_SUPPORTED_CONTROLLER_TYPES as readonly string[]).includes(type)

export interface MaaFWControllerInfo {
  name: string
  label?: string | null
  type: string
  description?: string | null
  icon?: string | null
  option: string[]
  permissionRequired: boolean
}

export interface MaaFWResourceInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  path: string[]
  controller: string[]
  option: string[]
}

export interface MaaFWGroupInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  defaultExpand: boolean
}

export interface MaaFWSettingInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  option: string[]
  defaultExpand: boolean
}

export interface MaaFWTaskInfo {
  name: string
  label?: string | null
  entry: string
  description?: string | null
  icon?: string | null
  group: string[]
  controller: string[]
  resource: string[]
  option: string[]
  defaultCheck: boolean
}

export interface MaaFWOptionCaseInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  option: string[]
}

export interface MaaFWOptionInputInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  default?: string | null
  pipelineType?: string | null
  verify?: string | null
  verifyError?: string | null
  patternMsg?: string | null
  /** PI v2.10.0：密码 / 密钥字段，掩码输入，保存后只拿得到密文 */
  password?: boolean
}

export interface MaaFWOptionInfo {
  name: string
  type: string
  label?: string | null
  description?: string | null
  icon?: string | null
  controller: string[]
  resource: string[]
  cases: MaaFWOptionCaseInfo[]
  inputs: MaaFWOptionInputInfo[]
  hotkeys: Array<{
    name: string
    label?: string | null
    description?: string | null
    default?: string | null
  }>
  defaultCase?: string | string[] | null
  /** PI v2.10.1：checkbox 最少 / 最多选择数，后端已放宽成自洽值；null 为不限 */
  minCount?: number | null
  maxCount?: number | null
}

export interface MaaFWAdbEmulatorExtraCapabilityInfo {
  screencap: boolean
  input: boolean
}

export interface MaaFWControlCapabilitiesInfo {
  emulatorExtras: Record<string, MaaFWAdbEmulatorExtraCapabilityInfo>
}

export interface MaaFWPresetInfo {
  name: string
  label?: string | null
  description?: string | null
  taskCount: number
  checkedCount: number
  snapshot: MaaFWTaskSnapshot
  controller?: string[]
  resource?: string[]
}

export interface MaaFWInterfacePreviewData {
  path: string
  project: MaaFWProjectInfo
  globalOption: string[]
  controlCapabilities: MaaFWControlCapabilitiesInfo
  controllers: MaaFWControllerInfo[]
  resources: MaaFWResourceInfo[]
  groups: MaaFWGroupInfo[]
  settings: MaaFWSettingInfo[]
  tasks: MaaFWTaskInfo[]
  options: MaaFWOptionInfo[]
  presets: MaaFWPresetInfo[]
  importCount: number
  agentCount: number
}

// HSR TaskMapping 默认值（Daily / ReceiveRewards / DivergentUniverse / CurrencyWars 默认走 SRA）
export const DEFAULT_HSR_TASK_MAPPING: HSRConfig_TaskMapping = {
  Daily: 'SRA',
  ReceiveRewards: 'SRA',
  DivergentUniverse: 'SRA',
  CurrencyWars: 'SRA',
}

/**
 * 解析 HSR 单个模块的执行脚本。
 * current 可用且在 available 中时优先保留，否则回退到仍可用的脚本。
 */
export function resolveTaskMappingValue(
  current: string | undefined,
  available: Set<'M7A' | 'SRA'>
): 'M7A' | 'SRA' | undefined {
  if (current && available.has(current as 'M7A' | 'SRA')) {
    return current as 'M7A' | 'SRA'
  }
  if (available.has('M7A')) return 'M7A'
  if (available.has('SRA')) return 'SRA'
  return undefined
}

// 脚本基础信息
export interface Script {
  id: string
  type: ScriptType
  name: string
  config:
    | MaaConfig
    | GeneralConfig
    | OkwwConfig
    | OkNteConfig
    | SrcConfig
    | MaaEndConfig
    | MaaFWScriptConfig
    | HSRConfig
    | BetterGIConfig
    | BAAHConfig
  users: User[]
}

// 用户配置
export interface User {
  id: string
  name: string
  Data: {
    LastProxyDate: string
    GreenTicketStoreMonth?: string
    ProxyTimes: number
  }
  Info: {
    Annihilation: string
    Id: string
    InfrastMode: string
    InfrastName: string
    MedicineNumb: number
    Mode: string
    Name: string
    SanityMode?: string
    Notes: string
    Password: string
    Resource?: string
    RemainedDay: number
    IfUseMasConfig?: boolean
    SeriesNumb: string
    Server: string
    Stage: string
    StageMode: string
    Stage_1: string
    Stage_2: string
    Stage_3: string
    Status: boolean
    Tag?: string | null // 用户标签列表（JSON字符串，TagItem的dict列表）
  }
  Notify: {
    Enabled: boolean
    IfSendMail: boolean
    IfSendSixStar: boolean
    IfSendStatistic: boolean
    IfServerChan: boolean
    ServerChanChannel: string
    ServerChanKey: string
    ServerChanTag: string
    ToAddress: string
  }
  /** 仅 ZzzOd 用户携带：游戏账号区（标签展示消费 GameRegion/Account/BilibiliAccountName） */
  Game?: {
    GameRegion?: 'cn' | 'cn_b' | 'us' | 'eu' | 'asia' | 'twhkmo' | null
    Account?: string | null
    BilibiliAccountName?: string | null
  }
  Task: {
    IfInfrast: boolean
    IfFight: boolean
    IfMall: boolean
    IfAward: boolean
    IfSwitchTheme: boolean
    IfRecruit: boolean
    IfStartUp: boolean
    Queue?: unknown
    IfActivityFirst?: boolean
    ActivityStageIndex?: number
    ActivityMedicineNumb?: number
    IfDepotMaintain?: boolean
    DepotMaintainPlans?: string
    IfGreenTicketStore?: boolean
    SanityTaskType?: MaaEndTaskConfig['SanityTaskType']
    OperatorProgression?: MaaEndTaskConfig['OperatorProgression']
    WeaponProgression?: MaaEndTaskConfig['WeaponProgression']
    CrisisDrills?: MaaEndTaskConfig['CrisisDrills']
    RewardsSetOption?: MaaEndTaskConfig['RewardsSetOption']
    AutoEssenceSpecifiedLocation?: MaaEndTaskConfig['AutoEssenceSpecifiedLocation']
    AutoEssenceMenu?: MaaEndTaskConfig['AutoEssenceMenu']
    AutoEssenceTargetWeapons?: MaaEndTaskConfig['AutoEssenceTargetWeapons']
  }
  QFluentWidgets: {
    ThemeColor: string
    ThemeMode: string
  }
}

// 脚本索引项
export interface ScriptIndexItem {
  uid: string
  type:
    | 'MaaConfig'
    | 'GeneralConfig'
    | 'OkwwConfig'
    | 'OkNteConfig'
    | 'SrcConfig'
    | 'MaaEndConfig'
    | 'M9AConfig'
    | 'MaaFWConfig'
    | 'HSRConfig'
    | 'BetterGIConfig'
    | 'ZzzOdConfig'
    | 'BAAHConfig'
}

// 脚本详情（用于前端展示）
export interface ScriptDetail {
  uid: string
  type: ScriptType
  name: string
  config:
    | MaaConfig
    | GeneralConfig
    | OkwwConfig
    | OkNteConfig
    | SrcConfig
    | MaaEndConfig
    | MaaFWScriptConfig
    | HSRConfig
    | BetterGIConfig
    | ZzzOdConfig
    | BAAHConfig
  users?: User[]
  createTime?: string
}
