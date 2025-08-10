/// <reference types="vite/client" />

declare global {
  interface Window {
    electronAPI: {
      // 开发工具
      openDevTools: () => Promise<void>
      selectFolder: () => Promise<string | null>
      selectFile: (filters?: Array<{ name: string; extensions: string[] }>) => Promise<string | null>
      
      // 管理员权限检查
      checkAdmin: () => Promise<boolean>
      
      // 环境检查
      checkEnvironment: () => Promise<{
        pythonExists: boolean
        gitExists: boolean
        backendExists: boolean
        dependenciesInstalled: boolean
        isInitialized: boolean
      }>
      
      // 关键文件检查
      checkCriticalFiles: () => Promise<{
        pythonExists: boolean
        pipExists: boolean
        gitExists: boolean
        mainPyExists: boolean
      }>
      
      // Python相关
      downloadPython: (mirror: string) => Promise<{ success: boolean; error?: string }>
      deletePython: () => Promise<{ success: boolean; error?: string }>
      
      // pip相关
      installPip: () => Promise<{ success: boolean; error?: string }>
      deletePip: () => Promise<{ success: boolean; error?: string }>
      
      // Git相关
      downloadGit: () => Promise<{ success: boolean; error?: string }>
      deleteGit: () => Promise<{ success: boolean; error?: string }>
      checkGitUpdate: () => Promise<{ hasUpdate: boolean; error?: string }>
      
      // 后端代码相关
      cloneBackend: (gitUrl: string) => Promise<{ success: boolean; error?: string }>
      updateBackend: (gitUrl: string) => Promise<{ success: boolean; error?: string }>
      
      // 依赖安装
      installDependencies: (mirror: string) => Promise<{ success: boolean; error?: string }>
      
      // 后端服务
      startBackend: () => Promise<{ success: boolean; error?: string }>
      
      // 下载进度监听
      onDownloadProgress: (callback: (progress: {
        progress: number
        status: string
        message: string
      }) => void) => void
      removeDownloadProgressListener: () => void
    }
  }
}
