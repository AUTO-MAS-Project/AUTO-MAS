declare global {
  interface ElectronAPI {
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
    checkCriticalFiles: () => Promise<{ pythonExists: boolean; gitExists: boolean; mainPyExists: boolean }>
    checkGitUpdate: () => Promise<{ hasUpdate: boolean; error?: string }>
    downloadPython: (mirror?: string) => Promise<any>
    installPip: () => Promise<any>
    downloadGit: () => Promise<any>
    installDependencies: (mirror?: string) => Promise<any>
    cloneBackend: (repoUrl?: string) => Promise<any>
    updateBackend: (repoUrl?: string) => Promise<any>
    startBackend: () => Promise<{ success: boolean; error?: string }>
    stopBackend?: () => Promise<{ success: boolean; error?: string }>

    // 管理员权限相关
    checkAdmin: () => Promise<boolean>
    restartAsAdmin: () => Promise<void>

    // 配置文件操作
    saveConfig: (config: any) => Promise<void>
    loadConfig: () => Promise<any>
    resetConfig: () => Promise<void>

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
    resizeDialogWindow: (height: number) => Promise<void>

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
  }

  interface Window {
    electronAPI: ElectronAPI
  }
}