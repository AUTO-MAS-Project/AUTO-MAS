// Electron API 类型定义
export interface ElectronAPI {
  openDevTools: () => Promise<void>
  selectFolder: () => Promise<string | null>
  selectFile: (filters?: any[]) => Promise<string[]>
  openUrl: (url: string) => Promise<{ success: boolean; error?: string }>

  // 窗口控制
  windowMinimize: () => Promise<void>
  windowMaximize: () => Promise<void>
  windowClose: () => Promise<void>
  windowIsMaximized: () => Promise<boolean>
  windowFocus: () => Promise<void>
  appQuit: () => Promise<void>

  // 进程管理
  getRelatedProcesses: () => Promise<any[]>
  killAllProcesses: () => Promise<{ success: boolean; error?: string }>

  // 初始化相关API
  checkEnvironment: () => Promise<any>
  checkCriticalFiles: () => Promise<{
    pythonExists: boolean
    gitExists: boolean
    mainPyExists: boolean
  }>
  checkGitUpdate: () => Promise<{ hasUpdate: boolean; error?: string }>
  downloadPython: (mirror?: string) => Promise<any>
  installPip: () => Promise<any>
  downloadGit: () => Promise<any>
  installDependencies: (mirror?: string) => Promise<any>
  cloneBackend: (repoUrl?: string) => Promise<any>
  updateBackend: (repoUrl?: string) => Promise<any>
  startBackend: () => Promise<{ success: boolean; error?: string }>
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
  saveConfig: (config: any) => Promise<void>
  loadConfig: () => Promise<any>
  resetConfig: () => Promise<void>

  // 托盘设置
  updateTraySettings: (uiSettings: any) => Promise<boolean>
  syncBackendConfig: (backendSettings: any) => Promise<boolean>

  // 日志文件操作
  getLogPath: () => Promise<string>
  getLogFiles: () => Promise<string[]>
  getLogs: (lines?: number, fileName?: string) => Promise<string>
  clearLogs: (fileName?: string) => Promise<void>
  cleanOldLogs: (daysToKeep?: number) => Promise<void>

  // 日志写入
  logWrite: (level: string, module: string, message: string) => Promise<void>

  // 日志解析
  parseBackendLog: (logLine: string) => Promise<any>
  processLogColors: (logContent: string, enableColorHighlight: boolean) => Promise<string>

  // 保留原有方法以兼容现有代码
  saveLogsToFile: (logs: string) => Promise<void>
  loadLogsFromFile: () => Promise<string | null>

  // 文件系统操作
  openFile: (filePath: string) => Promise<void>
  showItemInFolder: (filePath: string) => Promise<void>

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
  onDownloadProgress: (callback: (progress: any) => void) => void
  removeDownloadProgressListener: () => void

  // ==================== 初始化 API ====================

  // 单步初始化API
  initMirrors: () => Promise<{ success: boolean; error?: string }>
  installPython: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  installPip: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  installGit: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  pullRepository: (targetBranch?: string, selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  installDependencies: (selectedMirror?: string) => Promise<{ success: boolean; error?: string; skipped?: boolean }>
  getMirrors: (type: string) => Promise<any[]>

  // API 端点获取
  getApiEndpoint: (key: string) => Promise<string>
  getApiEndpoints: () => Promise<{ local: string; websocket: string }>

  // 完整初始化流程（保留用于兼容）
  initialize: (targetBranch?: string, startBackend?: boolean) => Promise<{
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
  backendStart: () => Promise<{ success: boolean; error?: string }>
  backendStop: () => Promise<{ success: boolean; error?: string }>
  backendRestart: () => Promise<{ success: boolean; error?: string }>
  backendStatus: () => Promise<{
    isRunning: boolean
    pid?: number
    startTime?: Date
    wsConnected: boolean
    lastPingTime?: Date
    error?: string
  }>

  // 清理资源
  cleanup: () => Promise<{ success: boolean }>

  // 监听单步进度
  onPythonProgress: (callback: (progress: any) => void) => void
  removePythonProgressListener?: () => void
  onPipProgress: (callback: (progress: any) => void) => void
  removePipProgressListener?: () => void
  onGitProgress: (callback: (progress: any) => void) => void
  removeGitProgressListener?: () => void
  onRepositoryProgress: (callback: (progress: any) => void) => void
  removeRepositoryProgressListener?: () => void
  onDependencyProgress: (callback: (progress: any) => void) => void
  removeDependencyProgressListener?: () => void

  // 监听初始化进度（保留用于兼容）
  onInitializationProgress: (callback: (progress: {
    stage: string
    stageIndex: number
    totalStages: number
    progress: number
    message: string
  }) => void) => void
  removeInitializationProgressListener?: () => void

  // 监听后端状态
  onBackendStatus: (callback: (status: {
    isRunning: boolean
    pid?: number
    startTime?: Date
    wsConnected: boolean
    lastPingTime?: Date
    error?: string
  }) => void) => void
  removeBackendStatusListener?: () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
