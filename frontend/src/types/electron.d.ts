// Electron API 类型定义
export interface ElectronAPI {
  // 窗口类型标识
  isDialogWindow: () => boolean

  openDevTools: () => Promise<void>
  selectFolder: () => Promise<string | null>
  selectFile: (filters?: any[]) => Promise<string[]>
  openUrl: (url: string) => Promise<{ success: boolean; error?: string }>

  // 窗口控制
  windowMinimize: () => Promise<void>
  windowMaximize: () => Promise<void>
  windowClose: () => Promise<void>
  windowIsMaximized: () => Promise<boolean>
  appQuit: () => Promise<void>

  // 进程管理
  getRelatedProcesses: () => Promise<any[]>
  killAllProcesses: () => Promise<{ success: boolean; error?: string }>
  forceExit: () => Promise<{ success: boolean }>

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
  stopBackend?: () => Promise<{ success: boolean; error?: string }>

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

  // 保留原有方法以兼容现有代码
  saveLogsToFile: (logs: string) => Promise<void>
  loadLogsFromFile: () => Promise<string | null>

  // 文件系统操作
  openFile: (filePath: string) => Promise<void>
  showItemInFolder: (filePath: string) => Promise<void>

  // 对话框相关
  showQuestionDialog: (questionData: {
    title?: string
    message?: string
    options?: string[]
    messageId?: string
  }) => Promise<boolean>
  dialogResponse: (messageId: string, choice: boolean) => Promise<boolean>

  // 主题信息获取
  getThemeInfo: () => Promise<{
    themeMode: string
    themeColor: string
    actualTheme: string
    systemTheme: string
    isDark: boolean
    primaryColor: string
  }>

  // 监听下载进度
  onDownloadProgress: (callback: (progress: any) => void) => void
  removeDownloadProgressListener: () => void

  // ==================== V2 初始化 API ====================

  // 单步初始化API
  v2InitMirrors: () => Promise<{ success: boolean; error?: string }>
  v2InstallPython: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  v2InstallPip: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  v2InstallGit: (selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  v2PullRepository: (targetBranch?: string, selectedMirror?: string) => Promise<{ success: boolean; error?: string }>
  v2InstallDependencies: (selectedMirror?: string) => Promise<{ success: boolean; error?: string; skipped?: boolean }>
  v2GetMirrors: (type: string) => Promise<any[]>

  // 完整初始化流程（保留用于兼容）
  v2Initialize: (targetBranch?: string, startBackend?: boolean) => Promise<{
    success: boolean
    error?: string
    completedStages: string[]
    failedStage?: string
  }>

  // 仅更新模式
  v2UpdateOnly: (targetBranch?: string) => Promise<{
    success: boolean
    error?: string
    completedStages: string[]
    failedStage?: string
  }>

  // 后端服务管理
  v2BackendStart: () => Promise<{ success: boolean; error?: string }>
  v2BackendStop: () => Promise<{ success: boolean; error?: string }>
  v2BackendRestart: () => Promise<{ success: boolean; error?: string }>
  v2BackendStatus: () => Promise<{
    isRunning: boolean
    pid?: number
    startTime?: Date
    wsConnected: boolean
    lastPingTime?: Date
    error?: string
  }>

  // 清理资源
  v2Cleanup: () => Promise<{ success: boolean }>

  // 监听单步进度
  onV2PythonProgress: (callback: (progress: any) => void) => void
  removeV2PythonProgressListener?: () => void
  onV2PipProgress: (callback: (progress: any) => void) => void
  removeV2PipProgressListener?: () => void
  onV2GitProgress: (callback: (progress: any) => void) => void
  removeV2GitProgressListener?: () => void
  onV2RepositoryProgress: (callback: (progress: any) => void) => void
  removeV2RepositoryProgressListener?: () => void
  onV2DependencyProgress: (callback: (progress: any) => void) => void
  removeV2DependencyProgressListener?: () => void

  // 监听 V2 初始化进度（保留用于兼容）
  onV2InitializationProgress: (callback: (progress: {
    stage: string
    stageIndex: number
    totalStages: number
    progress: number
    message: string
  }) => void) => void
  removeV2InitializationProgressListener?: () => void

  // 监听 V2 后端日志
  onV2BackendLog: (callback: (log: string) => void) => void
  removeV2BackendLogListener?: () => void

  // 监听 V2 后端状态
  onV2BackendStatus: (callback: (status: {
    isRunning: boolean
    pid?: number
    startTime?: Date
    wsConnected: boolean
    lastPingTime?: Date
    error?: string
  }) => void) => void
  removeV2BackendStatusListener?: () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
