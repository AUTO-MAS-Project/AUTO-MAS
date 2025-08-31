import { contextBridge, ipcRenderer } from 'electron'

window.addEventListener('DOMContentLoaded', () => {
  console.log('Preload loaded')
})

// 暴露安全的 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  openDevTools: () => ipcRenderer.invoke('open-dev-tools'),
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  selectFile: (filters?: any[]) => ipcRenderer.invoke('select-file', filters),
  openUrl: (url: string) => ipcRenderer.invoke('open-url', url),

  // 初始化相关API
  checkEnvironment: () => ipcRenderer.invoke('check-environment'),
  downloadPython: (mirror?: string) => ipcRenderer.invoke('download-python', mirror),
  installPip: () => ipcRenderer.invoke('install-pip'),
  downloadGit: () => ipcRenderer.invoke('download-git'),
  installDependencies: (mirror?: string) => ipcRenderer.invoke('install-dependencies', mirror),
  cloneBackend: (repoUrl?: string) => ipcRenderer.invoke('clone-backend', repoUrl),
  updateBackend: (repoUrl?: string) => ipcRenderer.invoke('update-backend', repoUrl),
  startBackend: () => ipcRenderer.invoke('start-backend'),

  // 管理员权限相关
  checkAdmin: () => ipcRenderer.invoke('check-admin'),
  restartAsAdmin: () => ipcRenderer.invoke('restart-as-admin'),

  // 配置文件操作
  saveConfig: (config: any) => ipcRenderer.invoke('save-config', config),
  loadConfig: () => ipcRenderer.invoke('load-config'),
  resetConfig: () => ipcRenderer.invoke('reset-config'),

  // 日志文件操作
  saveLogsToFile: (logs: string) => ipcRenderer.invoke('save-logs-to-file', logs),
  loadLogsFromFile: () => ipcRenderer.invoke('load-logs-from-file'),

  // 监听下载进度
  onDownloadProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('download-progress', (_, progress) => callback(progress))
  },
  removeDownloadProgressListener: () => {
    ipcRenderer.removeAllListeners('download-progress')
  },
})
