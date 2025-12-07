import { contextBridge, ipcRenderer } from 'electron'

window.addEventListener('DOMContentLoaded', () => {
  // 预加载脚本已加载
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
  windowFocus: () => ipcRenderer.invoke('window-focus'),
  appQuit: () => ipcRenderer.invoke('app-quit'),
  appRestart: () => ipcRenderer.invoke('app-restart'),

  // 进程管理
  getRelatedProcesses: () => ipcRenderer.invoke('get-related-processes'),
  killAllProcesses: () => ipcRenderer.invoke('kill-all-processes'),

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

  // 仓库管理
  checkRepoStatus: () => ipcRenderer.invoke('check-repo-status'),
  cleanRepo: () => ipcRenderer.invoke('clean-repo'),
  getRepoInfo: () => ipcRenderer.invoke('get-repo-info'),

  // 后端管理
  startBackend: () => ipcRenderer.invoke('backend-start'),
  stopBackend: () => ipcRenderer.invoke('backend-stop'),

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
  getLogPath: () => ipcRenderer.invoke('log:getPath'),
  getLogFiles: () => ipcRenderer.invoke('log:getFiles'),
  getLogs: (lines?: number, fileName?: string) => ipcRenderer.invoke('log:getContent', lines, fileName),
  clearLogs: (fileName?: string) => ipcRenderer.invoke('log:clear', fileName),
  cleanOldLogs: (daysToKeep?: number) => ipcRenderer.invoke('log:cleanOldLogs'),

  // 日志写入
  logWrite: (level: string, module: string, message: string) => ipcRenderer.invoke('log:write', level, module, message),

  // 日志解析
  parseBackendLog: (logLine: string) => ipcRenderer.invoke('log:parseBackendLog', logLine),
  processLogColors: (logContent: string, enableColorHighlight: boolean) => ipcRenderer.invoke('log:processLogColors', logContent, enableColorHighlight),

  // 日志管理服务
  logManagement: {
    // 初始化
    initialize: (config?: any) => ipcRenderer.invoke('logManagement:initialize', config),

    // 日志处理
    processLog: (rawLog: string, source?: string) => ipcRenderer.invoke('logManagement:processLog', rawLog, source),
    processBatchLogs: (rawLogs: string[], source?: string) => ipcRenderer.invoke('logManagement:processBatchLogs', rawLogs, source),

    // 日志订阅
    subscribe: (id: string, filter?: any) => ipcRenderer.invoke('logManagement:subscribe', id, filter),
    unsubscribe: (id: string) => ipcRenderer.invoke('logManagement:unsubscribe', id),
    toggleSubscriber: (id: string, enabled: boolean) => ipcRenderer.invoke('logManagement:toggleSubscriber', id, enabled),

    // 日志获取
    getLogs: (conditions?: any, limit?: number, offset?: number) => ipcRenderer.invoke('logManagement:getLogs', conditions, limit, offset),
    exportLogs: (conditions?: any, format?: string) => ipcRenderer.invoke('logManagement:exportLogs', conditions, format),
    clearLogs: () => ipcRenderer.invoke('logManagement:clearLogs'),

    // 统计信息
    getStats: () => ipcRenderer.invoke('logManagement:getStats'),
    resetStats: () => ipcRenderer.invoke('logManagement:resetStats'),

    // 配置管理
    getConfig: () => ipcRenderer.invoke('logManagement:getConfig'),
    updateConfig: (config: any) => ipcRenderer.invoke('logManagement:updateConfig', config),

    // 订阅者管理
    getSubscribers: () => ipcRenderer.invoke('logManagement:getSubscribers')
  },

  // 日志管道
  logPipeline: {
    // 配置
    getConfig: () => ipcRenderer.invoke('logPipeline:getConfig'),
    updateConfig: (config: any) => ipcRenderer.invoke('logPipeline:updateConfig', config),

    // 解析器管理
    getParserStats: () => ipcRenderer.invoke('logPipeline:getParserStats'),
    toggleParser: (parserName: string, enabled: boolean) => ipcRenderer.invoke('logPipeline:toggleParser', parserName, enabled),

    // 缓存管理
    clearCache: () => ipcRenderer.invoke('logPipeline:clearCache'),
    getCacheStats: () => ipcRenderer.invoke('logPipeline:getCacheStats'),

    // 批处理
    flush: () => ipcRenderer.invoke('logPipeline:flush'),
    getBatchStats: () => ipcRenderer.invoke('logPipeline:getBatchStats')
  },

  // 保留原有方法以兼容现有代码
  saveLogsToFile: (logs: string) => ipcRenderer.invoke('save-logs-to-file', logs),
  loadLogsFromFile: () => ipcRenderer.invoke('load-logs-from-file'),

  // 文件系统操作
  openFile: (filePath: string) => ipcRenderer.invoke('open-file', filePath),
  showItemInFolder: (filePath: string) => ipcRenderer.invoke('show-item-in-folder', filePath),

  // 主题信息获取
  getThemeInfo: () => ipcRenderer.invoke('get-theme-info'),
  getTheme: () => ipcRenderer.invoke('get-theme'),
  getAppPath: (name: string) => ipcRenderer.invoke('get-app-path', name),

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

  // 监听后端状态
  onBackendStatus: (callback: (status: any) => void) => {
    ipcRenderer.on('backend-status', (_, status) => callback(status))
  },
  removeBackendStatusListener: () => {
    ipcRenderer.removeAllListeners('backend-status')
  },

  // 监听日志管理服务事件
  onLogManagementEvent: (callback: (event: string, data: any) => void) => {
    ipcRenderer.on('log-management-event', (_, event, data) => callback(event, data))
  },
  removeLogManagementEventListener: () => {
    ipcRenderer.removeAllListeners('log-management-event')
  },

  // 监听日志更新
  onLogUpdate: (callback: (logs: any[]) => void) => {
    ipcRenderer.on('log-update', (_, logs) => callback(logs))
  },
  removeLogUpdateListener: () => {
    ipcRenderer.removeAllListeners('log-update')
  },

  // 监听日志统计更新
  onLogStatsUpdate: (callback: (stats: any) => void) => {
    ipcRenderer.on('log-stats-update', (_, stats) => callback(stats))
  },
  removeLogStatsUpdateListener: () => {
    ipcRenderer.removeAllListeners('log-stats-update')
  },
})
