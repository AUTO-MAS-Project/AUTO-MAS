import { contextBridge, ipcRenderer } from 'electron'

window.addEventListener('DOMContentLoaded', () => {
  console.log('预加载脚本已加载')
})

// 暴露安全的 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  openDevTools: () => ipcRenderer.invoke('open-dev-tools'),
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  selectFile: (filters?: any[]) => ipcRenderer.invoke('select-file', filters),
  openUrl: (url: string) => ipcRenderer.invoke('open-url', url),

  // 窗口控制
  windowMinimize: () => ipcRenderer.invoke('window-minimize'),
  windowMaximize: () => ipcRenderer.invoke('window-maximize'),
  windowClose: () => ipcRenderer.invoke('window-close'),
  windowIsMaximized: () => ipcRenderer.invoke('window-is-maximized'),

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
  getLogPath: () => ipcRenderer.invoke('get-log-path'),
  getLogFiles: () => ipcRenderer.invoke('get-log-files'),
  getLogs: (lines?: number, fileName?: string) => ipcRenderer.invoke('get-logs', lines, fileName),
  clearLogs: (fileName?: string) => ipcRenderer.invoke('clear-logs', fileName),
  cleanOldLogs: (daysToKeep?: number) => ipcRenderer.invoke('clean-old-logs', daysToKeep),
  
  // 保留原有方法以兼容现有代码
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
