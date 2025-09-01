export interface ElectronAPI {
  openDevTools: () => Promise<void>
  selectFolder: () => Promise<string | null>
  selectFile: (filters?: any[]) => Promise<string | null>
  openUrl: (url: string) => Promise<{ success: boolean; error?: string }>

  // 初始化相关API
  checkEnvironment: () => Promise<{
    pythonExists: boolean
    gitExists: boolean
    backendExists: boolean
    dependenciesInstalled: boolean
    isInitialized: boolean
  }>
  downloadPython: (mirror?: string) => Promise<{ success: boolean; error?: string }>
  downloadGit: () => Promise<{ success: boolean; error?: string }>
  installDependencies: (mirror?: string) => Promise<{ success: boolean; error?: string }>
  cloneBackend: (repoUrl?: string) => Promise<{ success: boolean; error?: string }>
  updateBackend: (repoUrl?: string) => Promise<{ success: boolean; error?: string }>
  startBackend: () => Promise<{ success: boolean; error?: string }>
  
  // 日志文件操作
  saveLogsToFile: (logs: string) => Promise<void>
  loadLogsFromFile: () => Promise<string | null>
  
  // 监听下载进度
  onDownloadProgress: (callback: (progress: any) => void) => void
  removeDownloadProgressListener: () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}