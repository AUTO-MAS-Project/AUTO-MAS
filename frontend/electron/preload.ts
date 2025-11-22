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
  installPip: () => ipcRenderer.invoke('install-pip'),
  downloadGit: () => ipcRenderer.invoke('download-git'),
  checkGitUpdate: () => ipcRenderer.invoke('check-git-update'),
  installDependencies: (mirror?: string) => ipcRenderer.invoke('install-dependencies', mirror),
  cloneBackend: (repoUrl?: string) => ipcRenderer.invoke('clone-backend', repoUrl),
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

  // ==================== V2 初始化 API ====================

  // 单步初始化API
  v2InitMirrors: () => ipcRenderer.invoke('v2:init-mirrors'),
  v2InstallPython: (selectedMirror?: string) => ipcRenderer.invoke('v2:install-python', selectedMirror),
  v2InstallPip: (selectedMirror?: string) => ipcRenderer.invoke('v2:install-pip', selectedMirror),
  v2InstallGit: (selectedMirror?: string) => ipcRenderer.invoke('v2:install-git', selectedMirror),
  v2PullRepository: (targetBranch?: string, selectedMirror?: string) =>
    ipcRenderer.invoke('v2:pull-repository', targetBranch, selectedMirror),
  v2InstallDependencies: (selectedMirror?: string) =>
    ipcRenderer.invoke('v2:install-dependencies', selectedMirror),
  v2GetMirrors: (type: string) => ipcRenderer.invoke('v2:get-mirrors', type),

  // 完整初始化流程（保留用于兼容）
  v2Initialize: (targetBranch?: string, startBackend?: boolean) =>
    ipcRenderer.invoke('v2:initialize', targetBranch, startBackend),

  // 仅更新模式
  v2UpdateOnly: (targetBranch?: string) =>
    ipcRenderer.invoke('v2:update-only', targetBranch),

  // 后端服务管理
  v2BackendStart: () => ipcRenderer.invoke('v2:backend-start'),
  v2BackendStop: () => ipcRenderer.invoke('v2:backend-stop'),
  v2BackendRestart: () => ipcRenderer.invoke('v2:backend-restart'),
  v2BackendStatus: () => ipcRenderer.invoke('v2:backend-status'),

  // 清理资源
  v2Cleanup: () => ipcRenderer.invoke('v2:cleanup'),

  // 监听单步进度
  onV2PythonProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('v2:python-progress', (_, progress) => callback(progress))
  },
  removeV2PythonProgressListener: () => {
    ipcRenderer.removeAllListeners('v2:python-progress')
  },

  onV2PipProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('v2:pip-progress', (_, progress) => callback(progress))
  },
  removeV2PipProgressListener: () => {
    ipcRenderer.removeAllListeners('v2:pip-progress')
  },

  onV2GitProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('v2:git-progress', (_, progress) => callback(progress))
  },
  removeV2GitProgressListener: () => {
    ipcRenderer.removeAllListeners('v2:git-progress')
  },

  onV2RepositoryProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('v2:repository-progress', (_, progress) => callback(progress))
  },
  removeV2RepositoryProgressListener: () => {
    ipcRenderer.removeAllListeners('v2:repository-progress')
  },

  onV2DependencyProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('v2:dependency-progress', (_, progress) => callback(progress))
  },
  removeV2DependencyProgressListener: () => {
    ipcRenderer.removeAllListeners('v2:dependency-progress')
  },

  // 监听 V2 初始化进度（保留用于兼容）
  onV2InitializationProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('v2:initialization-progress', (_, progress) => callback(progress))
  },
  removeV2InitializationProgressListener: () => {
    ipcRenderer.removeAllListeners('v2:initialization-progress')
  },

  // 监听 V2 后端日志
  onV2BackendLog: (callback: (log: string) => void) => {
    ipcRenderer.on('v2:backend-log', (_, log) => callback(log))
  },
  removeV2BackendLogListener: () => {
    ipcRenderer.removeAllListeners('v2:backend-log')
  },

  // 监听 V2 后端状态
  onV2BackendStatus: (callback: (status: any) => void) => {
    ipcRenderer.on('v2:backend-status', (_, status) => callback(status))
  },
  removeV2BackendStatusListener: () => {
    ipcRenderer.removeAllListeners('v2:backend-status')
  },
})
