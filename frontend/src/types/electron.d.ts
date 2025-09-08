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

  // 初始化相关API
  checkEnvironment: () => Promise<any>
  downloadPython: (mirror?: string) => Promise<any>
  installPip: () => Promise<any>
  downloadGit: () => Promise<any>
  installDependencies: (mirror?: string) => Promise<any>
  cloneBackend: (repoUrl?: string) => Promise<any>
  updateBackend: (repoUrl?: string) => Promise<any>
  startBackend: () => Promise<any>

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

  // 监听下载进度
  onDownloadProgress: (callback: (progress: any) => void) => void
  removeDownloadProgressListener: () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}