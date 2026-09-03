import type { GlobalConfig_UI, GlobalConfig_Update } from '@/api'

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
  UI?: GlobalConfig_UI & {
    TrayItems?: unknown[]
    [key: string]: unknown
  }
  Update?: GlobalConfig_Update & {
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface ElectronMirrorSource {
  name: string
  url: string
  type: 'official' | 'mirror'
  description: string
}

export type ElectronMirrorType = 'python' | 'get_pip' | 'git' | 'repo' | 'pip_mirror'
export type ElectronApiEndpointKey = 'local' | 'websocket'

// ==================== Runtime 后端更新 ====================

/** 后端启动链路：`off` 走原有的自行启动 python.exe，其余两种由 Runtime 监督。 */
export type RuntimeLaunchMode = 'off' | 'development' | 'managed'

/** 更新失败的三类结局，界面据此决定给什么按钮。 */
export type RuntimeUpdatePhase = 'shutdown' | 'bootstrap' | 'restart'

export type RuntimeUpdateRetryAction =
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

/**
 * Runtime 灰度开关的三态。
 *
 * `off` 是原有的自装 Python / pip / Git 链路，另外两态由 auto-mas-runtime.exe 接管；
 * 主进程没给这个字段时（旧版本主进程、旧链路进度）界面一律按 `off` 处理。
 */
export type RuntimeInitMode = 'off' | 'development' | 'managed'

/** 初始化界面开局问一次的 Runtime 上下文。 */
export interface RuntimeInitContext {
  mode: RuntimeInitMode
  /** Runtime 没给 logPath 时「打开日志」退回的文件。 */
  fallbackLogPath: string
  /** 各段在 Runtime 链路下可选的镜像键；空数组表示该段不展示镜像选择。 */
  mirrorKeys: Record<string, string[]>
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
 * 旧链路一律缺省，所以全是可选的；界面按这些机器字段决定给哪些按钮，
 * 绝不解析 `error` 里的中文文案。
 */
export interface RuntimeFailureFields {
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

/** 单步安装与重试的返回形状：旧链路只有前两项，Runtime 链路额外带结构化字段。 */
export type InstallStageResult = {
  success: boolean
  error?: string
} & RuntimeFailureFields

// ==================== Runtime 灰度开关 ====================

/** Runtime 灰度开关的持久化设置取值；`auto` 表示跟随构建默认值。 */
export type RuntimeLaunchModeSetting = 'auto' | 'off' | 'development' | 'managed'
/** 最终生效值来自哪一级。 */
export type RuntimeLaunchModeSource = 'env' | 'setting' | 'default'

export interface RuntimeLaunchModeState {
  /** 持久化设置里存的原始值，用于回填选择控件。 */
  persisted: RuntimeLaunchModeSetting
  /** 本次实际生效的模式（`auto` 已被解析成具体值）。 */
  mode: 'off' | 'development' | 'managed'
  source: RuntimeLaunchModeSource
}

export interface ElectronAPI {
  openDevTools: () => Promise<void>
  selectFolder: () => Promise<string | null>
  selectFile: (filters?: unknown[]) => Promise<string[]>
  openUrl: (url: string) => Promise<{ success: boolean; error?: string }>
  discoverOkwwPath: () => Promise<PathDiscoveryResult>
  discoverWutheringWavesPath: () => Promise<PathDiscoveryResult>

  // 窗口控制
  windowMinimize: () => Promise<void>
  windowMaximize: () => Promise<void>
  windowClose: () => Promise<void>
  appRestart: () => Promise<void>
  windowIsMaximized: () => Promise<boolean>
  windowFocus: () => Promise<void>
  appQuit: () => Promise<void>

  // 系统休眠恢复与主进程关闭请求（生命周期协调器消费）
  onSystemResume?: (callback: () => void) => () => void
  onAppCloseRequested?: (callback: () => void) => () => void

  // 窗口可见性/后台状态
  getWindowActivity?: () => Promise<'visible' | 'background'>
  onWindowActivityChange: (callback: (activity: 'visible' | 'background') => void) => () => void

  // 进程管理
  getRelatedProcesses: () => Promise<RelatedProcess[]>
  killAllProcesses: () => Promise<{ success: boolean; error?: string }>

  // 初始化相关API
  checkEnvironment: () => Promise<unknown>
  checkCriticalFiles: () => Promise<{
    pythonExists: boolean
    gitExists: boolean
    mainPyExists: boolean
    pipExists?: boolean
    /** doctor 的逐项检查，只有 Runtime 链路产生，供失败态的「运行诊断」展示。 */
    runtimeChecks?: RuntimeDoctorCheck[]
  }>
  checkGitUpdate: () => Promise<{ hasUpdate: boolean; error?: string }>
  downloadPython: (mirror?: string) => Promise<unknown>
  downloadGit: () => Promise<unknown>
  // installDependencies 的权威声明在下面的「单步初始化API」里，这里原有的一份签名已过时
  cloneBackend: (repoUrl?: string) => Promise<unknown>
  updateBackend: (repoUrl?: string) => Promise<unknown>
  startBackend: () => Promise<{ success: boolean; error?: string; logs?: string }>
  stopBackend: () => Promise<{ success: boolean; error?: string }>

  // 快速安装相关
  downloadQuickEnvironment: () => Promise<{ success: boolean; error?: string }>
  extractQuickEnvironment: () => Promise<{ success: boolean; error?: string }>
  downloadQuickSource: () => Promise<{ success: boolean; error?: string }>
  extractQuickSource: () => Promise<{ success: boolean; error?: string }>
  updateQuickSource: (repoUrl?: string) => Promise<{ success: boolean; error?: string }>

  // 新增的git管理方法
  checkRepoStatus: () => Promise<{
    exists: boolean
    isGitRepo: boolean
    currentBranch?: string
    currentCommit?: string
    error?: string
  }>
  cleanRepo: () => Promise<{ success: boolean; error?: string }>
  getRepoInfo: () => Promise<{
    success: boolean
    info?: {
      repoExists: boolean
      isGitRepo: boolean
      currentBranch?: string
      currentCommit?: string
      remoteUrl?: string
      lastUpdate?: string
    }
    error?: string
  }>

  // 管理员权限相关
  checkAdmin: () => Promise<boolean>
  restartAsAdmin: () => Promise<void>

  // 配置文件操作
  saveConfig: (config: unknown) => Promise<void>
  loadConfig: () => Promise<ElectronConfig | null>
  resetConfig: () => Promise<void>

  // 应用初始化版本（保存前端版本号用于比对）
  getInitializedVersion: () => Promise<string | null>
  setInitializedVersion: (version: string) => Promise<boolean>

  // Runtime 灰度开关：持久化设置 + 当前生效值与来源，重启后生效。
  // `mode` 同时是标题栏更新入口走哪条链路的判据。
  getRuntimeLaunchMode: () => Promise<RuntimeLaunchModeState>
  setRuntimeLaunchMode: (mode: RuntimeLaunchModeSetting) => Promise<RuntimeLaunchModeState>

  // 托盘设置
  updateTraySettings: (uiSettings: unknown) => Promise<boolean>
  updateTrayConfig: (trayItems: unknown) => Promise<boolean>
  onTrayActionRequest: (
    callback: (request: {
      action: 'quit' | 'restart' | 'startTask'
      taskId?: string
      label?: string
    }) => void
  ) => () => void
  syncBackendConfig: (backendSettings: unknown) => Promise<boolean>

  // 日志文件操作
  exportLogs: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  exportMaaEndIssueReport: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
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
  exportDataBackup: () => Promise<{
    success: boolean
    message?: string
    zipPath?: string
    error?: string
  }>
  getLogs: (lines?: number, fileName?: string) => Promise<string>

  // 获取模块化日志器（使用主进程配置）
  getLogger: (moduleName: string) => {
    debug: (...args: unknown[]) => Promise<void>
    info: (...args: unknown[]) => Promise<void>
    warn: (...args: unknown[]) => Promise<void>
    error: (...args: unknown[]) => Promise<void>
  }

  // 保留原有方法以兼容现有代码
  saveLogsToFile: (logs: string) => Promise<void>
  loadLogsFromFile: () => Promise<string | null>

  // 文件系统操作
  openFile: (filePath: string) => Promise<void>
  showItemInFolder: (filePath: string) => Promise<void>
  fileExists: (filePath: string) => Promise<boolean>
  readFile: (filePath: string) => Promise<string>

  // 主题信息获取
  getThemeInfo: () => Promise<{
    themeMode: string
    themeColor: string
    actualTheme: string
    systemTheme: string
    isDark: boolean
    primaryColor: string
  }>
  getAppPath: (name: string) => Promise<string>

  // 监听下载进度
  onDownloadProgress: (callback: (progress: unknown) => void) => void
  removeDownloadProgressListener: () => void

  // ==================== 初始化 API ====================

  // 单步初始化API
  initMirrors: () => Promise<{ success: boolean; error?: string }>
  // rebuild 对应失败态的「重建环境」按钮，只在 Runtime 链路下有意义
  installPython: (selectedMirror?: string, rebuild?: boolean) => Promise<InstallStageResult>
  installPip: (selectedMirror?: string, rebuild?: boolean) => Promise<InstallStageResult>
  installGit: (selectedMirror?: string, rebuild?: boolean) => Promise<InstallStageResult>
  pullRepository: (
    targetBranch?: string,
    selectedMirror?: string,
    rebuild?: boolean
  ) => Promise<InstallStageResult>
  installDependencies: (
    selectedMirror?: string,
    rebuild?: boolean
  ) => Promise<InstallStageResult & { skipped?: boolean }>
  getMirrors: (type: ElectronMirrorType) => Promise<ElectronMirrorSource[]>
  /** 初始化界面开局问一次：走没走 Runtime、回退日志文件、各段可用镜像键。 */
  getRuntimeInitContext?: () => Promise<RuntimeInitContext>

  // API 端点获取
  getApiEndpoint: (key: ElectronApiEndpointKey) => Promise<string>
  getApiEndpoints: () => Promise<{ local: string; websocket: string }>

  // 完整初始化流程（保留用于兼容）
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

  // 仅更新模式
  updateOnly: (targetBranch?: string) => Promise<{
    success: boolean
    error?: string
    completedStages: string[]
    failedStage?: string
  }>

  // 后端服务管理
  backendStart: () => Promise<InstallStageResult>
  backendStop: () => Promise<{ success: boolean; error?: string }>
  backendRestart: () => Promise<InstallStageResult>
  backendStatus: () => Promise<{
    isRunning: boolean
    pid?: number
    startTime?: Date
    wsConnected: boolean
    lastPingTime?: Date
    error?: string
    /** 本次生命周期是否走 Runtime 监督链路；true 时后端只能由 Electron 经 Runtime 停止。 */
    runtimeSupervised?: boolean
  }>

  // Runtime 链路的后端更新（启动模式统一走上面的 getRuntimeLaunchMode）
  updateBackendViaRuntime: (targetVersion: string) => Promise<RuntimeUpdateOutcome>
  retryBackendUpdate: (action: RuntimeUpdateRetryAction) => Promise<RuntimeUpdateOutcome>
  cancelBackendUpdate: () => Promise<{ accepted: boolean; forwarded: boolean }>
  onBackendUpdateProgress: (callback: (progress: RuntimeUpdateProgress) => void) => void
  removeBackendUpdateProgressListener?: () => void

  // 清理资源
  cleanup: () => Promise<{ success: boolean }>

  // 监听单步进度
  onPythonProgress: (callback: (progress: unknown) => void) => void
  removePythonProgressListener?: () => void
  onPipProgress: (callback: (progress: unknown) => void) => void
  removePipProgressListener?: () => void
  onGitProgress: (callback: (progress: unknown) => void) => void
  removeGitProgressListener?: () => void
  onRepositoryProgress: (callback: (progress: unknown) => void) => void
  removeRepositoryProgressListener?: () => void
  onDependencyProgress: (callback: (progress: unknown) => void) => void
  removeDependencyProgressListener?: () => void

  // 监听初始化进度（保留用于兼容）
  onInitializationProgress: (
    callback: (progress: {
      stage: string
      stageIndex: number
      totalStages: number
      progress: number
      message: string
      /** Runtime 链路给出的机器可读段状态；旧链路不产生。 */
      status?: 'started' | 'running' | 'completed' | 'failed'
      /** 本条进度来自哪条链路；旧链路不产生，按 off 处理。 */
      runtimeMode?: RuntimeInitMode
    }) => void
  ) => void
  removeInitializationProgressListener?: () => void

  // 监听后端状态
  onBackendStatus: (
    callback: (status: {
      isRunning: boolean
      pid?: number
      startTime?: Date
      wsConnected: boolean
      lastPingTime?: Date
      error?: string
    }) => void
  ) => void
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
