import type { FluxdownInstallOut, GlobalConfig_UI, GlobalConfig_Update } from '@/api'
import type { AnalyticsContext, RendererAnalyticsEvent } from '@/types/analytics'
import type { FrontendCloseRequest } from '@/types/appLifecycle'
import type { AppearanceCategory, MascotImportResult, MascotSummary } from '@/types/mascotPack'
import type {
  DesktopMascotHostAPI,
  DesktopMascotSelection,
  DesktopMascotTaskHostAPI,
} from '@/types/desktopMascot'
import type {
  AppearanceCleanupResult,
  AppearanceImportResult,
  InstalledAppearance,
  LocalAppearanceInspectResult,
  OnlineAppearanceCoverResult,
  OnlineAppearanceDetailResult,
  OnlineAppearanceInstallResult,
  OnlineAppearanceListResult,
  OnlineAppearancePrepareResult,
  OnlineAppearanceQuery,
} from '@/types/appearance'

// Electron API 类型定义
export interface PathDiscoveryCandidate {
  path: string
  channel?: 'China' | 'Global'
}

export interface PathDiscoveryResult {
  success: boolean
  candidates?: PathDiscoveryCandidate[]
  path?: string
  channel?: 'China' | 'Global'
  error?: string
}

export interface RelatedProcess {
  pid: number
  name: string
  commandLine?: string
  command?: string
}

export interface ElectronConfig {
  confirmBeforeClose?: boolean
  lastCloseAction?: 'quit' | 'tray'
  UI?: GlobalConfig_UI & {
    TrayItems?: unknown[]
    [key: string]: unknown
  }
  Update?: GlobalConfig_Update & {
    [key: string]: unknown
  }
  [key: string]: unknown
}

export type ElectronApiEndpointKey = 'local' | 'websocket'

// ==================== Runtime 后端更新 ====================

/** 后端启动模式：开发源码或受管工作区，均由 Runtime 监督。 */
export type RuntimeLaunchMode = 'development' | 'managed'

export interface RuntimeBinaryUpdateResult {
  status: 'upgraded' | 'current' | 'skipped' | 'cancelled' | 'failed'
  target?: { version: string }
  error?: string
}

export interface RuntimeBinaryUpdateCheck {
  status: 'available' | 'current' | 'skipped' | 'unavailable'
  currentVersion?: string | null
  target?: { version: string }
  error?: string
}

export interface RuntimeBinaryProgress {
  /** Electron 更新器提供的目标版本与当前下载尝试；旧事件可缺省。 */
  targetVersion?: string
  sourceName?: string
  sourceIndex?: number
  sourceCount?: number
  source?: string
  /** Electron 更新器的正常阶段；旧事件缺失时保留原文。 */
  phase?: 'check' | 'download' | 'complete'
  progress: number
  message: string
}

/** 更新失败的三类结局，界面据此决定给什么按钮。 */
export type RuntimeUpdatePhase = 'shutdown' | 'bootstrap' | 'restart'

export type RuntimeUpdateRetryAction =
  | 'bootstrap'
  | 'workspace-sync'
  | 'dependencies-sync'
  | 'dependencies-rebuild'
  | 'repair'

export type RuntimeUpdateStage =
  | 'shutdown'
  | 'mirror'
  | 'python'
  | 'pip'
  | 'git'
  | 'repository'
  | 'dependency'
  | 'backend'
  | 'restart'

export interface RuntimeUpdateProgress {
  stage: RuntimeUpdateStage
  status: 'started' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
}

export interface RuntimeUpdateOutcome {
  success: boolean
  phase?: RuntimeUpdatePhase
  error?: string
  code?: string
  retryable?: boolean
  remediation?: string[]
  logs?: string
  logPath?: string
  retryActions?: RuntimeUpdateRetryAction[]
  /** 重试已无意义（不可重试 / INTERNAL_ERROR / contact-support），只能携带日志反馈。 */
  supportRequired?: boolean
  cancelled?: boolean
  unsupported?: boolean
}

// ==================== Runtime 初始化界面 ====================

/** Runtime 初始化模式。 */
export type RuntimeInitMode = 'development' | 'managed'

/** 初始化界面开局问一次的 Runtime 上下文。 */
export interface RuntimeInitContext {
  mode: RuntimeInitMode
  /** Runtime 没给 logPath 时「打开日志」退回的文件。 */
  fallbackLogPath: string
}

/** Runtime doctor 的单项检查结果。 */
export interface RuntimeDoctorCheck {
  id: string
  name: string
  message: string
  /** 实测取值为 `ok` / `missing` / `error`。 */
  status: string
  details: Record<string, unknown>
}

/**
 * Runtime 链路失败时随结果一起给出的结构化字段。
 *
 * 启动前失败可能没有结构化字段；界面按可用的机器字段决定给哪些按钮，
 * 绝不解析 `error` 里的中文文案。
 */
export interface RuntimeFailureFields {
  /** Runtime 第 0 步失败的实际来源；界面仍沿用 failedStage。 */
  failureOrigin?: 'runtime_binary'
  /** Runtime 结果码，如 `MIRROR_EXHAUSTED` / `INTERNAL_ERROR`。 */
  code?: string
  retryable?: boolean
  /** 处置动作，如 `retry` / `retry-other-mirror` / `open-log`；未知取值忽略即可。 */
  remediation?: string[]
  /** `[stdout]…\n\n[stderr]…` 整块文本。 */
  logs?: string
  /** Runtime 本次操作的日志文件路径。 */
  logPath?: string
}

/** 单步准备与重试的返回形状，失败时携带 Runtime 结构化字段。 */
export type InstallStageResult = {
  success: boolean
  error?: string
  failedStage?: string
} & RuntimeFailureFields

// ==================== Runtime 启动模式 ====================

/** 最终生效值来自哪一级。 */
export type RuntimeLaunchModeSource = 'env' | 'default'

/** 日志页增量读取的返回，与主进程 electron/services/logFileReader.ts 一致 */
export interface LogIncrement {
  /** 新增内容；reset 为 true 时是当前全文 */
  content: string
  /** 读取后的字节偏移，下一次从这里继续 */
  size: number
  /** 文件变小或消失（轮转/清空）时为 true，应整体替换 */
  reset: boolean
}

/** 与主进程 electron/services/backendService.ts 的 BackendStatus 一致 */
export interface BackendStatus {
  isRunning: boolean
  pid?: number
  startTime?: Date
  error?: string
  /** 本次生命周期是否走 Runtime 监督链路；true 时后端只能由 Electron 经 Runtime 停止。 */
  runtimeSupervised: boolean
}

export interface RuntimeLaunchModeState {
  /** 本次实际生效的模式。 */
  mode: 'development' | 'managed'
  source: RuntimeLaunchModeSource
}

/** 真实显示器回来了但有任务在跑时，后端发来的询问数据（与 WSDisplayDetachPromptData 一致） */
export interface VirtualDisplayPromptPayload {
  returned: string[]
  monitor?: { left: number; top: number; right: number; bottom: number } | null
}

export interface ElectronAPI extends DesktopMascotHostAPI, DesktopMascotTaskHostAPI {
  appUpdateCheck(
    input: import('../../electron/services/appUpdateTypes').AppUpdateSettings
  ): Promise<import('../../electron/services/appUpdateTypes').AppUpdateCheck>
  appUpdateStatus(): Promise<import('../../electron/services/appUpdateTypes').AppUpdateSnapshot>
  appUpdateStart(
    version: string,
    input: import('../../electron/services/appUpdateTypes').AppUpdateSettings,
    downloader?: 'builtin' | 'fluxdown'
  ): Promise<{ code: number; message?: string }>
  appUpdateCancel(): Promise<{ code: number; message?: string }>
  appUpdateSwitch(): Promise<{ code: number; message?: string }>
  appUpdateInstall(): Promise<{ code: number; message?: string }>
  onAppUpdate(
    callback: (event: import('../../electron/services/appUpdateTypes').AppUpdateEvent) => void
  ): () => void
  analytics?: {
    getContext: () => Promise<AnalyticsContext>
    trackEvent: (context: number, event: RendererAnalyticsEvent) => void
  }
  isMacOS: boolean
  installFluxdown: (mirror: string) => Promise<FluxdownInstallOut>
  listMascots?: () => Promise<MascotSummary[]>
  importMascot?: (zipPath: string, replace?: boolean) => Promise<MascotImportResult>
  removeMascot?: (id: string) => Promise<{ success: boolean; error?: string }>
  /** 不带选择状态时表示资源列表变化。 */
  onMascotChanged?: (callback: (selection?: DesktopMascotSelection) => void) => () => void
  openDevTools: () => Promise<void>
  selectFolder: () => Promise<string | null>
  selectFile: (filters?: unknown[]) => Promise<string[]>
  saveTextFile: (
    defaultName: string,
    content: string,
    filters?: unknown[],
    dialogOptions?: { dialogTitle?: string; buttonLabel?: string }
  ) => Promise<{ success: boolean; filePath?: string; error?: string }>
  openUrl: (url: string) => Promise<{ success: boolean; error?: string }>
  discoverOkwwPath: () => Promise<PathDiscoveryResult>
  discoverWutheringWavesPath: () => Promise<PathDiscoveryResult>

  // 窗口控制
  windowMinimize: () => Promise<boolean>
  windowMaximize: () => Promise<void>
  windowClose: () => Promise<void>
  windowHideToTray: () => Promise<boolean>
  notifyRendererReady?: () => void
  notifyNativeCloseHandlerReady?: () => void
  appRestart: () => Promise<void>
  /** 只标记「这次退出后重新拉起」，退出本身仍走 appQuit；后端请求的重启用它 */
  appRestartOnQuit?: () => Promise<void>
  windowIsMaximized: () => Promise<boolean>
  onWindowMaximizedChange: (callback: (maximized: boolean) => void) => () => void
  windowFocus: () => Promise<void>
  onNativeWindowCloseRequested?: (callback: () => void) => () => void
  /** 电源操作倒计时开始：把窗口拉到最前并临时置顶 */
  powerWarningStart?: () => Promise<void>
  /** 倒计时结束或取消：撤回置顶 */
  powerWarningEnd?: () => Promise<void>
  appQuit: () => Promise<void>
  appObserveBackendClose?: (request?: FrontendCloseRequest) => void
  /** 等待用户确认期间暂停退出兜底，保留关闭请求锁。 */
  appWaitForQuitConfirmation?: () => Promise<boolean>
  /** 保存前领取退出凭证；准备超时不会强制关闭后端。 */
  appPrepareQuit?: () => Promise<number | null>
  /** 保存完成后确认凭证仍有效，开始关闭后端的兜底计时。 */
  appConfirmQuit?: (token: number) => Promise<boolean>
  /** 页面保存失败：撤销协调退出，取消兜底计时并重新显示窗口。 */
  appCancelQuit?: (token?: number) => Promise<void>

  // 系统休眠恢复与主进程关闭请求（生命周期协调器消费）
  onSystemResume?: (callback: () => void) => () => void
  onAppCloseRequested?: (callback: (confirmRunningTasks: boolean) => void) => () => void

  // 窗口可见性/后台状态
  getWindowActivity?: () => Promise<'visible' | 'background'>
  onWindowActivityChange: (callback: (activity: 'visible' | 'background') => void) => () => void

  // 进程管理
  getRelatedProcesses: () => Promise<RelatedProcess[]>
  killAllProcesses: () => Promise<{ success: boolean; error?: string }>

  // 初始化相关API
  checkCriticalFiles: () => Promise<{
    pythonExists: boolean
    gitExists: boolean
    mainPyExists: boolean
    pipExists?: boolean
    /** doctor 的逐项检查，只有 Runtime 链路产生，供失败态的「运行诊断」展示。 */
    runtimeChecks?: RuntimeDoctorCheck[]
  }>
  startBackend: () => Promise<{ success: boolean; error?: string; logs?: string }>
  stopBackend: () => Promise<{ success: boolean; error?: string }>

  // 配置文件操作
  // 仅覆盖 config 中的字段；defaults 只补齐文件中缺失的字段。
  saveConfig: (config: unknown, defaults?: unknown) => Promise<void>
  loadConfig: () => Promise<ElectronConfig | null>
  resetConfig: () => Promise<void>

  // 应用初始化版本（保存前端版本号用于比对）
  getInitializedVersion: () => Promise<string | null>
  setInitializedVersion: (version: string) => Promise<boolean>

  // Runtime 当前生效模式与来源（只读）。
  // `mode` 同时是标题栏更新入口走哪条链路的判据。
  getRuntimeLaunchMode: () => Promise<RuntimeLaunchModeState>

  // 托盘设置
  updateTraySettings: (uiSettings: unknown) => Promise<boolean>
  updateTrayConfig: (trayItems: unknown) => Promise<boolean>
  onTrayActionRequest: (
    callback: (request: { action: 'quit' | 'startTask'; taskId?: string; label?: string }) => void
  ) => () => void
  syncBackendConfig: (backendSettings: unknown) => Promise<boolean>

  // 日志文件操作
  exportLogs: (dialogLabels?: { title: string; zipFilterName: string }) => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    skippedPaths?: string[]
    errorCode?: 'window-unavailable' | 'directory-missing' | 'no-files'
    error?: string
  }>
  exportMaaIssueReport: (dialogLabels?: { title: string; zipFilterName: string }) => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
    errorCode?: 'no-installation' | 'no-files' | 'export-failed'
    collectedCount?: number
    incompleteCount?: number
  }>
  exportMaaEndIssueReport: () => Promise<{
    success: boolean
    message?: string
    directoryPaths?: string[]
    incompleteCount?: number
    error?: string
  }>
  exportOkwwIssueReport: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  exportOkNteIssueReport: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  exportZzzOdIssueReport: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  exportWhimboxIssueReport: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  exportBetterGIIssueReport: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  /** configTypes：要列出的脚本配置类名（MaaFW 特调注册表的 scriptConfigType） */
  listMaaFWIssueReportScripts: (configTypes: string[]) => Promise<
    Array<{
      uid: string
      type: string
      name: string
      projectLabel: string
    }>
  >
  exportMaaFWIssueReport: (scriptId: string) => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  exportM9AIssueReport: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  exportMSSIssueReport: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  exportDataBackup: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  /** 不传 fromOffset 返回整份字符串；传了只返回该字节偏移之后的新增部分。 */
  getLogs: {
    (lines?: number, fileName?: string): Promise<string>
    (lines: number, fileName: string, fromOffset: number): Promise<LogIncrement>
  }
  /** file 指定打开时选中哪一份日志，省略则沿用日志页自己的默认（后端日志）。 */
  openLogWindow: (file?: 'app' | 'frontend') => Promise<{ success: boolean; error?: string }>
  /** 日志窗已经开着时，主进程用它通知日志页换到请求的那一份。 */
  onLogSelectFile?: (callback: (file: 'app' | 'frontend') => void) => void
  removeLogSelectFileListener?: () => void

  // 虚拟显示器询问弹窗：主窗口把后端消息转给主进程另开窗口放到真实屏右下角
  showVirtualDisplayPrompt?: (
    payload: VirtualDisplayPromptPayload
  ) => Promise<{ success: boolean; error?: string }>
  observeVirtualDisplayPrompt?: () => void
  detachVirtualDisplayFromPrompt: () => Promise<import('@/api').VirtualDisplayDetachOut | null>
  closeVirtualDisplayPrompt?: () => Promise<void>
  /** 弹窗页面挂载后自己来取当前那一份数据；没有待处理的提示时为 null */
  getVirtualDisplayPrompt?: () => Promise<VirtualDisplayPromptPayload | null>
  onVirtualDisplayPromptData?: (
    callback: (payload: VirtualDisplayPromptPayload) => void
  ) => () => void

  // 获取模块化日志器（使用主进程配置）
  getLogger: (moduleName: string) => {
    debug: (...args: unknown[]) => Promise<void>
    info: (...args: unknown[]) => Promise<void>
    warn: (...args: unknown[]) => Promise<void>
    error: (...args: unknown[]) => Promise<void>
  }

  // 文件系统操作
  openFile: (filePath: string) => Promise<{ success: boolean; error?: string }>
  showItemInFolder: (filePath: string) => Promise<void>
  fileExists: (filePath: string) => Promise<boolean>
  readFile: (filePath: string) => Promise<string>
  /** 按 base64 读二进制文件（音频等）；渲染进程用它拼 data URL */
  readFileBase64: (filePath: string, maxBytes?: number) => Promise<{ base64: string; size: number }>

  getAppPath: (name: string) => Promise<string>

  // 自定义外观包
  listAppearances?: () => Promise<InstalledAppearance[]>
  getAppearance?: (id: string) => Promise<InstalledAppearance | null>
  importAppearance?: (zipPath: string, replace?: boolean) => Promise<AppearanceImportResult>
  removeAppearance?: (id: string) => Promise<{ success: boolean; error?: string }>
  clearInvalidAppearance?: (expectedId: string) => Promise<AppearanceCleanupResult>
  listOnlineAppearances?: (
    query?: OnlineAppearanceQuery,
    category?: AppearanceCategory
  ) => Promise<OnlineAppearanceListResult>
  getOnlineAppearance?: (
    fileKey: string,
    category?: AppearanceCategory
  ) => Promise<OnlineAppearanceDetailResult>
  prepareOnlineAppearance?: (
    fileKey: string,
    versionNo: number,
    category?: AppearanceCategory
  ) => Promise<OnlineAppearancePrepareResult>
  installOnlineAppearance?: (
    token: string,
    replace?: boolean,
    category?: AppearanceCategory
  ) => Promise<OnlineAppearanceInstallResult>
  discardOnlineAppearance?: (
    token: string,
    category?: AppearanceCategory
  ) => Promise<{ success: boolean }>
  getOnlineAppearanceCover?: (
    fileKey: string,
    versionNo?: number,
    category?: AppearanceCategory
  ) => Promise<OnlineAppearanceCoverResult>
  inspectLocalAppearance?: (
    zipPath: string,
    category?: AppearanceCategory
  ) => Promise<LocalAppearanceInspectResult>
  inspectAppearanceCover?: (
    imagePath: string
  ) => Promise<{ success: boolean; dataUrl?: string; error?: string }>
  onAppearanceChanged?: (callback: () => void) => () => void
  onThemeConfigChanged?: (callback: (config: unknown) => void) => () => void

  // ==================== 初始化 API ====================

  // 单步初始化API
  // rebuild 对应失败态的「重建环境」按钮。
  installPython: (rebuild?: boolean) => Promise<InstallStageResult>
  pullRepository: (rebuild?: boolean) => Promise<InstallStageResult>
  installDependencies: (rebuild?: boolean) => Promise<InstallStageResult & { skipped?: boolean }>
  /** 初始化界面的运行模式与回退日志文件。 */
  getRuntimeInitContext: () => Promise<RuntimeInitContext>
  updateRuntimeBinary: () => Promise<RuntimeBinaryUpdateResult>
  checkRuntimeBinaryUpdate: () => Promise<RuntimeBinaryUpdateCheck>
  onRuntimeBinaryProgress: (callback: (progress: RuntimeBinaryProgress) => void) => void
  removeRuntimeBinaryProgressListener: () => void

  // API 端点获取
  getApiEndpoint: (key: ElectronApiEndpointKey) => Promise<string>

  // Runtime 完整初始化流程
  initialize: (
    targetBranch?: string,
    startBackend?: boolean
  ) => Promise<
    {
      success: boolean
      error?: string
      completedStages: string[]
      failedStage?: string
    } & RuntimeFailureFields
  >

  waitDesktopStartup: () => Promise<
    ({ success: boolean; error?: string; failedStage?: string } & RuntimeFailureFields) | null
  >
  desktopStartupStatus: () => Promise<{
    runtimeMode: RuntimeInitMode
    flowKind: 'startup' | 'first-run' | 'update'
    fullInitialization: boolean
    state: 'running' | 'ready' | 'failed'
    progress: Array<{
      stage: string
      progress: number
      message: string
      status?: 'started' | 'running' | 'completed' | 'failed'
    }>
  } | null>
  cancelDesktopStartup: () => Promise<void>

  // 后端服务管理
  backendStart: (retry?: boolean) => Promise<InstallStageResult>
  backendRestart: (reason?: 'manual' | 'recovery') => Promise<InstallStageResult>
  backendStatus: () => Promise<BackendStatus>
  checkRuntimeBackendUpdate: () => Promise<{
    updateAvailable: boolean
    staged?: boolean
    currentCommit?: string
    remoteCommit?: string
    commitMessage?: string
    error?: string
  }>

  // Runtime 链路的后端更新（启动模式统一走上面的 getRuntimeLaunchMode）
  updateBackendViaRuntime: (targetVersion: string) => Promise<RuntimeUpdateOutcome>
  retryBackendUpdate: (action: RuntimeUpdateRetryAction) => Promise<RuntimeUpdateOutcome>
  cancelBackendUpdate: () => Promise<{ accepted: boolean; forwarded: boolean }>
  onBackendUpdateProgress: (callback: (progress: RuntimeUpdateProgress) => void) => void
  removeBackendUpdateProgressListener?: () => void

  // 监听完整初始化进度
  onInitializationProgress: (
    callback: (progress: {
      stage: string
      stageIndex: number
      totalStages: number
      progress: number
      message: string
      /** Runtime 链路给出的机器可读段状态。 */
      status?: 'started' | 'running' | 'completed' | 'failed'
      /** 本条进度对应的 Runtime 模式。 */
      runtimeMode?: RuntimeInitMode
      /** 当前阶段没有可靠总量，应展示持续活动状态而不是精确百分比。 */
      indeterminate?: boolean
      /** 产生本条进度的 Runtime stage 原文（`network.probe` / `uv.download` …）。 */
      runtimeStage?: string
      /** 产生本条进度的 Runtime progress.status 原文。 */
      runtimeStatus?: string
      /** 当前条目：正在下载的文件名，或测速时的源 key。 */
      item?: string
      /** 当前字节来自哪个源的 key。 */
      source?: string
      /** Runtime 下载的目标版本与当前源尝试；旧事件可缺省。 */
      targetVersion?: string
      sourceName?: string
      sourceIndex?: number
      sourceCount?: number
      /** 最近 1 秒窗口的吞吐（字节/秒）。 */
      bytesPerSecond?: number
      /** 已下载字节数。 */
      current?: number
      /** 总字节数。 */
      total?: number
    }) => void
  ) => void
  removeInitializationProgressListener?: () => void

  // 监听后端状态
  onBackendStatus: (callback: (status: BackendStatus) => void) => void
  removeBackendStatusListener?: () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
    /** 调试用:由 WebSocketMessageListener 挂载的消息弹窗触发接口 */
    __debugShowQuestion?: (questionData: Record<string, unknown>) => Promise<void>
    /** 调试用:调度中心调试信息输出 */
    debugScheduler?: () => void
    /** 调试用:WebSocket 连接测试 */
    testWebSocketConnection?: () => Promise<void>
  }
}
