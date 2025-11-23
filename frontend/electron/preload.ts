import { contextBridge, ipcRenderer } from 'electron'

window.addEventListener('DOMContentLoaded', () => {
  console.log('预加载脚本已加载')
})

// 检查是否为对话框窗口
const isDialogWindow = process.argv.includes('--is-dialog-window')

// 暴露安全的 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 窗口类型标识
  isDialogWindow: () => isDialogWindow,
  openDevTools: () => ipcRenderer.invoke('open-dev-tools'),
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  selectFile: (filters?: any[]) => ipcRenderer.invoke('select-file', filters),
  openUrl: (url: string) => ipcRenderer.invoke('open-url', url),

  // 窗口控制
  windowMinimize: () => ipcRenderer.invoke('window-minimize'),
  windowMaximize: () => ipcRenderer.invoke('window-maximize'),
  windowClose: () => ipcRenderer.invoke('window-close'),
  windowIsMaximized: () => ipcRenderer.invoke('window-is-maximized'),
  appQuit: () => ipcRenderer.invoke('app-quit'),
  appRestart: () => ipcRenderer.invoke('app-restart'),

  // 进程管理
  getRelatedProcesses: () => ipcRenderer.invoke('get-related-processes'),
  killAllProcesses: () => ipcRenderer.invoke('kill-all-processes'),
  forceExit: () => ipcRenderer.invoke('force-exit'),

  // 初始化相关API
  checkEnvironment: () => ipcRenderer.invoke('check-environment'),
  checkCriticalFiles: () => ipcRenderer.invoke('check-critical-files'),
  downloadPython: (mirror?: string) => ipcRenderer.invoke('download-python', mirror),
  downloadGit: () => ipcRenderer.invoke('download-git'),
  checkGitUpdate: () => ipcRenderer.invoke('check-git-update'), cloneBackend: (repoUrl?: string) => ipcRenderer.invoke('clone-backend', repoUrl),
  updateBackend: (repoUrl?: string) => ipcRenderer.invoke('update-backend', repoUrl),
  // 快速安装相关
  downloadQuickEnvironment: () => ipcRenderer.invoke('download-quick-environment'),
  extractQuickEnvironment: () => ipcRenderer.invoke('extract-quick-environment'),
  downloadQuickSource: () => ipcRenderer.invoke('download-quick-source'),
  extractQuickSource: () => ipcRenderer.invoke('extract-quick-source'),
  updateQuickSource: (repoUrl?: string) => ipcRenderer.invoke('update-quick-source', repoUrl),

  // 新增的git管理方法
  checkRepoStatus: () => ipcRenderer.invoke('check-repo-status'),
  cleanRepo: () => ipcRenderer.invoke('clean-repo'),
  getRepoInfo: () => ipcRenderer.invoke('get-repo-info'),
  startBackend: () => ipcRenderer.invoke('start-backend'),
  stopBackend: () => ipcRenderer.invoke('stop-backend'),

  // 管理员权限相关
  checkAdmin: () => ipcRenderer.invoke('check-admin'),
  restartAsAdmin: () => ipcRenderer.invoke('restart-as-admin'),

  // 配置文件操作
  saveConfig: (config: any) => ipcRenderer.invoke('save-config', config),
  loadConfig: () => ipcRenderer.invoke('load-config'),
  resetConfig: () => ipcRenderer.invoke('reset-config'),

  // 托盘设置实时更新
  updateTraySettings: (uiSettings: any) => ipcRenderer.invoke('update-tray-settings', uiSettings),

  // 同步后端配置
  syncBackendConfig: (backendSettings: any) =>
    ipcRenderer.invoke('sync-backend-config', backendSettings),

  // 日志文件操作
  getLogPath: () => ipcRenderer.invoke('get-log-path'),
  getLogFiles: () => ipcRenderer.invoke('get-log-files'),
  getLogs: (lines?: number, fileName?: string) => ipcRenderer.invoke('get-logs', lines, fileName),
  clearLogs: (fileName?: string) => ipcRenderer.invoke('clear-logs', fileName),
  cleanOldLogs: (daysToKeep?: number) => ipcRenderer.invoke('clean-old-logs', daysToKeep),

  // 保留原有方法以兼容现有代码
  saveLogsToFile: (logs: string) => ipcRenderer.invoke('save-logs-to-file', logs),
  loadLogsFromFile: () => ipcRenderer.invoke('load-logs-from-file'),

  // 文件系统操作
  openFile: (filePath: string) => ipcRenderer.invoke('open-file', filePath),
  showItemInFolder: (filePath: string) => ipcRenderer.invoke('show-item-in-folder', filePath),

  // 对话框相关
  showQuestionDialog: (questionData: any) =>
    ipcRenderer.invoke('show-question-dialog', questionData),
  dialogResponse: (messageId: string, choice: boolean) =>
    ipcRenderer.invoke('dialog-response', messageId, choice),

  // 主题信息获取
  getThemeInfo: () => ipcRenderer.invoke('get-theme-info'),
  getTheme: () => ipcRenderer.invoke('get-theme'),

  // 监听下载进度
  onDownloadProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('download-progress', (_, progress) => callback(progress))
  },
  removeDownloadProgressListener: () => {
    ipcRenderer.removeAllListeners('download-progress')
  },

  // ==================== 初始化 API ====================

  // 单步初始化API
  initMirrors: () => ipcRenderer.invoke('init-mirrors'),
  installPython: (selectedMirror?: string) => ipcRenderer.invoke('install-python', selectedMirror),
  installPip: (selectedMirror?: string) => ipcRenderer.invoke('install-pip', selectedMirror),
  installGit: (selectedMirror?: string) => ipcRenderer.invoke('install-git', selectedMirror),
  pullRepository: (targetBranch?: string, selectedMirror?: string) =>
    ipcRenderer.invoke('pull-repository', targetBranch, selectedMirror),
  installDependencies: (selectedMirror?: string) =>
    ipcRenderer.invoke('install-dependencies', selectedMirror),
  getMirrors: (type: string) => ipcRenderer.invoke('get-mirrors', type),

  // 完整初始化流程（保留用于兼容）
  initialize: (targetBranch?: string, startBackend?: boolean) =>
    ipcRenderer.invoke('initialize', targetBranch, startBackend),

  // 仅更新模式
  updateOnly: (targetBranch?: string) =>
    ipcRenderer.invoke('update-only', targetBranch),

  // 后端服务管理
  backendStart: () => ipcRenderer.invoke('backend-start'),
  backendStop: () => ipcRenderer.invoke('backend-stop'),
  backendRestart: () => ipcRenderer.invoke('backend-restart'),
  backendStatus: () => ipcRenderer.invoke('backend-status'),

  // 清理资源
  cleanup: () => ipcRenderer.invoke('cleanup'),

  // 监听单步进度
  onPythonProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('python-progress', (_, progress) => callback(progress))
  },
  removePythonProgressListener: () => {
    ipcRenderer.removeAllListeners('python-progress')
  },

  onPipProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('pip-progress', (_, progress) => callback(progress))
  },
  removePipProgressListener: () => {
    ipcRenderer.removeAllListeners('pip-progress')
  },

  onGitProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('git-progress', (_, progress) => callback(progress))
  },
  removeGitProgressListener: () => {
    ipcRenderer.removeAllListeners('git-progress')
  },

  onRepositoryProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('repository-progress', (_, progress) => callback(progress))
  },
  removeRepositoryProgressListener: () => {
    ipcRenderer.removeAllListeners('repository-progress')
  },

  onDependencyProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('dependency-progress', (_, progress) => callback(progress))
  },
  removeDependencyProgressListener: () => {
    ipcRenderer.removeAllListeners('dependency-progress')
  },

  // 监听初始化进度（保留用于兼容）
  onInitializationProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('initialization-progress', (_, progress) => callback(progress))
  },
  removeInitializationProgressListener: () => {
    ipcRenderer.removeAllListeners('initialization-progress')
  },

  // 监听后端日志
  onBackendLog: (callback: (log: string) => void) => {
    ipcRenderer.on('backend-log', (_, log) => callback(log))
  },
  removeBackendLogListener: () => {
    ipcRenderer.removeAllListeners('backend-log')
  },

  // 监听后端状态
  onBackendStatus: (callback: (status: any) => void) => {
    ipcRenderer.on('backend-status', (_, status) => callback(status))
  },
  removeBackendStatusListener: () => {
    ipcRenderer.removeAllListeners('backend-status')
  },
})
