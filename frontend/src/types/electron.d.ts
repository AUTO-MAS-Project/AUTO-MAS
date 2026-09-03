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
  }>
  checkGitUpdate: () => Promise<{ hasUpdate: boolean; error?: string }>
  downloadPython: (mirror?: string) => Promise<unknown>
  downloadGit: () => Promise<unknown>
  installDependencies: (mirror?: string) => Promise<unknown>
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
  installPython: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  installPip: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  installGit: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  pullRepository: (
    targetBranch?: string,
    selectedMirror?: string
  ) => Promise<{ success: boolean; error?: string }>
  installDependencies: (
    selectedMirror?: string
  ) => Promise<{ success: boolean; error?: string; skipped?: boolean }>
  getMirrors: (type: ElectronMirrorType) => Promise<ElectronMirrorSource[]>

  // API 端点获取
  getApiEndpoint: (key: ElectronApiEndpointKey) => Promise<string>
  getApiEndpoints: () => Promise<{ local: string; websocket: string }>

  // 完整初始化流程（保留用于兼容）
  initialize: (
    targetBranch?: string,
    startBackend?: boolean
  ) => Promise<{
    success: boolean
    error?: string
    completedStages: string[]
    failedStage?: string
  }>

  // 仅更新模式
  updateOnly: (targetBranch?: string) => Promise<{
    success: boolean
    error?: string
    completedStages: string[]
    failedStage?: string
  }>

  // 后端服务管理
  backendStart: () => Promise<{ success: boolean; error?: string; logs?: string }>
  backendStop: () => Promise<{ success: boolean; error?: string }>
  backendRestart: () => Promise<{ success: boolean; error?: string; logs?: string }>
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
