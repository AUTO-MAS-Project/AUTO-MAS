import { contextBridge, ipcRenderer } from 'electron'

window.addEventListener('DOMContentLoaded', () => {
  // 预加载脚本已加载
})

// 暴露安全的 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  openDevTools: () => ipcRenderer.invoke('open-dev-tools'),
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  selectFile: (filters?: unknown[]) => ipcRenderer.invoke('select-file', filters),
  openUrl: (url: string) => ipcRenderer.invoke('open-url', url),
  discoverOkwwPath: () => ipcRenderer.invoke('okww-path-discovery:discover-okww'),
  discoverWutheringWavesPath: () =>
    ipcRenderer.invoke('okww-path-discovery:discover-wuthering-waves'),

  // 窗口控制
  windowMinimize: () => ipcRenderer.invoke('window-minimize'),
  windowMaximize: () => ipcRenderer.invoke('window-maximize'),
  windowClose: () => ipcRenderer.invoke('window-close'),
  windowIsMaximized: () => ipcRenderer.invoke('window-is-maximized'),
  windowFocus: () => ipcRenderer.invoke('window-focus'),
  appQuit: () => ipcRenderer.invoke('app-quit'),
  appRestart: () => ipcRenderer.invoke('app-restart'),

  // 系统休眠恢复与主进程关闭请求（生命周期协调器消费）
  onSystemResume: (callback: () => void) => {
    const listener = () => callback()
    ipcRenderer.on('system-resumed', listener)
    return () => ipcRenderer.removeListener('system-resumed', listener)
  },
  onAppCloseRequested: (callback: () => void) => {
    const listener = () => callback()
    ipcRenderer.on('app-close-requested', listener)
    return () => ipcRenderer.removeListener('app-close-requested', listener)
  },

  // 窗口可见性/后台状态
  getWindowActivity: () => ipcRenderer.invoke('get-window-activity'),
  onWindowActivityChange: (callback: (activity: 'visible' | 'background') => void) => {
    const listener = (_event: Electron.IpcRendererEvent, activity: unknown) => {
      if (activity === 'visible' || activity === 'background') {
        callback(activity)
      }
    }

    ipcRenderer.on('window-activity-changed', listener)
    return () => ipcRenderer.removeListener('window-activity-changed', listener)
  },

  // 进程管理
  getRelatedProcesses: () => ipcRenderer.invoke('get-related-processes'),
  killAllProcesses: () => ipcRenderer.invoke('kill-all-processes'),

  // 初始化相关API
  checkEnvironment: () => ipcRenderer.invoke('check-environment'),
  checkCriticalFiles: () => ipcRenderer.invoke('check-critical-files'),
  downloadPython: (mirror?: string) => ipcRenderer.invoke('download-python', mirror),
  downloadGit: () => ipcRenderer.invoke('download-git'),
  checkGitUpdate: () => ipcRenderer.invoke('check-git-update'),
  cloneBackend: (repoUrl?: string) => ipcRenderer.invoke('clone-backend', repoUrl),
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
  saveConfig: (config: unknown) => ipcRenderer.invoke('save-config', config),
  loadConfig: () => ipcRenderer.invoke('load-config'),
  resetConfig: () => ipcRenderer.invoke('reset-config'),

  // 应用初始化版本（保存前端版本号用于比对）
  getInitializedVersion: () => ipcRenderer.invoke('get-initialized-version'),
  setInitializedVersion: (version: string) =>
    ipcRenderer.invoke('set-initialized-version', version),

  // Runtime 灰度开关：持久化设置 + 当前生效值与来源
  getRuntimeLaunchMode: () => ipcRenderer.invoke('get-runtime-launch-mode'),
  setRuntimeLaunchMode: (mode: string) => ipcRenderer.invoke('set-runtime-launch-mode', mode),

  // 托盘设置实时更新
  updateTraySettings: (uiSettings: unknown) => ipcRenderer.invoke('update-tray-settings', uiSettings),

  // 托盘自定义菜单项
  updateTrayConfig: (trayItems: unknown) => ipcRenderer.invoke('update-tray-config', trayItems),

  // 托盘动作请求（由渲染进程统一处理：启动任务 / 退出 / 重启）
  onTrayActionRequest: (
    callback: (request: {
      action: 'quit' | 'restart' | 'startTask'
      taskId?: string
      label?: string
    }) => void
  ) => {
    const listener = (
      _event: Electron.IpcRendererEvent,
      request: {
        action: 'quit' | 'restart' | 'startTask'
        taskId?: string
        label?: string
      }
    ) => {
      callback(request)
    }

    ipcRenderer.on('tray-action-request', listener)
    return () => ipcRenderer.removeListener('tray-action-request', listener)
  },

  // 同步后端配置
  syncBackendConfig: (backendSettings: unknown) =>
    ipcRenderer.invoke('sync-backend-config', backendSettings),

  // 日志文件操作
  exportLogs: () => ipcRenderer.invoke('log:export'),
  exportMaaEndIssueReport: () => ipcRenderer.invoke('maaend:exportIssueReport'),
  exportOkwwIssueReport: () => ipcRenderer.invoke('okww:exportIssueReport'),
  exportOkNteIssueReport: () => ipcRenderer.invoke('oknte:exportIssueReport'),
  exportDataBackup: () => ipcRenderer.invoke('data:backup'),
  getLogs: (lines?: number, fileName?: string) =>
    ipcRenderer.invoke('log:getContent', lines, fileName),
  openLogWindow: () => ipcRenderer.invoke('log:openWindow'),

  // 获取模块化日志器（使用 electron-log）
  getLogger: (moduleName: string) => ({
    debug: (...args: unknown[]) => ipcRenderer.invoke('log:write', 'debug', moduleName, ...args),
    info: (...args: unknown[]) => ipcRenderer.invoke('log:write', 'info', moduleName, ...args),
    warn: (...args: unknown[]) => ipcRenderer.invoke('log:write', 'warn', moduleName, ...args),
    error: (...args: unknown[]) => ipcRenderer.invoke('log:write', 'error', moduleName, ...args),
  }),

  // 日志管理服务
  logManagement: {
    // 初始化
    initialize: (config?: unknown) => ipcRenderer.invoke('logManagement:initialize', config),

    // 日志处理
    processLog: (rawLog: string, source?: string) =>
      ipcRenderer.invoke('logManagement:processLog', rawLog, source),
    processBatchLogs: (rawLogs: string[], source?: string) =>
      ipcRenderer.invoke('logManagement:processBatchLogs', rawLogs, source),

    // 日志订阅
    subscribe: (id: string, filter?: unknown) =>
      ipcRenderer.invoke('logManagement:subscribe', id, filter),
    unsubscribe: (id: string) => ipcRenderer.invoke('logManagement:unsubscribe', id),
    toggleSubscriber: (id: string, enabled: boolean) =>
      ipcRenderer.invoke('logManagement:toggleSubscriber', id, enabled),

    // 日志获取
    getLogs: (conditions?: unknown, limit?: number, offset?: number) =>
      ipcRenderer.invoke('logManagement:getLogs', conditions, limit, offset),
    exportLogs: (conditions?: unknown, format?: string) =>
      ipcRenderer.invoke('logManagement:exportLogs', conditions, format),
    clearLogs: () => ipcRenderer.invoke('logManagement:clearLogs'),

    // 统计信息
    getStats: () => ipcRenderer.invoke('logManagement:getStats'),
    resetStats: () => ipcRenderer.invoke('logManagement:resetStats'),

    // 配置管理
    getConfig: () => ipcRenderer.invoke('logManagement:getConfig'),
    updateConfig: (config: unknown) => ipcRenderer.invoke('logManagement:updateConfig', config),

    // 订阅者管理
    getSubscribers: () => ipcRenderer.invoke('logManagement:getSubscribers'),
  },

  // 日志管道
  logPipeline: {
    // 配置
    getConfig: () => ipcRenderer.invoke('logPipeline:getConfig'),
    updateConfig: (config: unknown) => ipcRenderer.invoke('logPipeline:updateConfig', config),

    // 解析器管理
    getParserStats: () => ipcRenderer.invoke('logPipeline:getParserStats'),
    toggleParser: (parserName: string, enabled: boolean) =>
      ipcRenderer.invoke('logPipeline:toggleParser', parserName, enabled),

    // 缓存管理
    clearCache: () => ipcRenderer.invoke('logPipeline:clearCache'),
    getCacheStats: () => ipcRenderer.invoke('logPipeline:getCacheStats'),

    // 批处理
    flush: () => ipcRenderer.invoke('logPipeline:flush'),
    getBatchStats: () => ipcRenderer.invoke('logPipeline:getBatchStats'),
  },

  // 保留原有方法以兼容现有代码
  saveLogsToFile: (logs: string) => ipcRenderer.invoke('save-logs-to-file', logs),
  loadLogsFromFile: () => ipcRenderer.invoke('load-logs-from-file'),

  // 文件系统操作
  openFile: (filePath: string) => ipcRenderer.invoke('open-file', filePath),
  showItemInFolder: (filePath: string) => ipcRenderer.invoke('show-item-in-folder', filePath),
  readFile: (filePath: string) => ipcRenderer.invoke('read-file', filePath),
  fileExists: (filePath: string) => ipcRenderer.invoke('file-exists', filePath),

  // 主题信息获取
  getThemeInfo: () => ipcRenderer.invoke('get-theme-info'),
  getTheme: () => ipcRenderer.invoke('get-theme'),
  getAppPath: (name: string) => ipcRenderer.invoke('get-app-path', name),

  // 监听下载进度
  onDownloadProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('download-progress', (_, progress) => callback(progress))
  },
  removeDownloadProgressListener: () => {
    ipcRenderer.removeAllListeners('download-progress')
  },

  // ==================== 初始化 API ====================

  // 单步初始化API
  // rebuild 对应界面「重建环境」按钮，只在 Runtime 链路下有意义（走 repair / dependencies rebuild）
  initMirrors: () => ipcRenderer.invoke('init-mirrors'),
  installPython: (selectedMirror?: string, rebuild?: boolean) =>
    ipcRenderer.invoke('install-python', selectedMirror, rebuild),
  installPip: (selectedMirror?: string, rebuild?: boolean) =>
    ipcRenderer.invoke('install-pip', selectedMirror, rebuild),
  installGit: (selectedMirror?: string, rebuild?: boolean) =>
    ipcRenderer.invoke('install-git', selectedMirror, rebuild),
  pullRepository: (targetBranch?: string, selectedMirror?: string, rebuild?: boolean) =>
    ipcRenderer.invoke('pull-repository', targetBranch, selectedMirror, rebuild),
  installDependencies: (selectedMirror?: string, rebuild?: boolean) =>
    ipcRenderer.invoke('install-dependencies', selectedMirror, rebuild),
  getMirrors: (type: string) => ipcRenderer.invoke('get-mirrors', type),
  getRuntimeInitContext: () => ipcRenderer.invoke('get-runtime-init-context'),

  // API 端点获取
  getApiEndpoint: (key: string) => ipcRenderer.invoke('get-api-endpoint', key),
  getApiEndpoints: () => ipcRenderer.invoke('get-api-endpoints'),

  // 完整初始化流程（Runtime 首次初始化与旧链路共用）
  initialize: (targetBranch?: string, startBackend?: boolean) =>
    ipcRenderer.invoke('initialize', targetBranch, startBackend),

  // 仅更新模式
  updateOnly: (targetBranch?: string) => ipcRenderer.invoke('update-only', targetBranch),

  // 后端服务管理
  backendStart: () => ipcRenderer.invoke('backend-start'),
  backendStop: () => ipcRenderer.invoke('backend-stop'),
  backendRestart: () => ipcRenderer.invoke('backend-restart'),
  backendStatus: () => ipcRenderer.invoke('backend-status'),
  checkRuntimeBackendUpdate: () => ipcRenderer.invoke('check-runtime-backend-update'),

  // Runtime 链路的后端更新（启动模式复用上面的 getRuntimeLaunchMode）
  updateBackendViaRuntime: (targetVersion: string) =>
    ipcRenderer.invoke('update-backend-via-runtime', targetVersion),
  retryBackendUpdate: (action: string) => ipcRenderer.invoke('retry-backend-update', action),
  cancelBackendUpdate: () => ipcRenderer.invoke('cancel-backend-update'),
  onBackendUpdateProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('backend-update-progress', (_, progress) => callback(progress))
  },
  removeBackendUpdateProgressListener: () => {
    ipcRenderer.removeAllListeners('backend-update-progress')
  },

  // 清理资源
  cleanup: () => ipcRenderer.invoke('cleanup'),

  // 监听单步进度
  onPythonProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('python-progress', (_, progress) => callback(progress))
  },
  removePythonProgressListener: () => {
    ipcRenderer.removeAllListeners('python-progress')
  },

  onPipProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('pip-progress', (_, progress) => callback(progress))
  },
  removePipProgressListener: () => {
    ipcRenderer.removeAllListeners('pip-progress')
  },

  onGitProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('git-progress', (_, progress) => callback(progress))
  },
  removeGitProgressListener: () => {
    ipcRenderer.removeAllListeners('git-progress')
  },

  onRepositoryProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('repository-progress', (_, progress) => callback(progress))
  },
  removeRepositoryProgressListener: () => {
    ipcRenderer.removeAllListeners('repository-progress')
  },

  onDependencyProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('dependency-progress', (_, progress) => callback(progress))
  },
  removeDependencyProgressListener: () => {
    ipcRenderer.removeAllListeners('dependency-progress')
  },

  // 监听完整初始化进度
  onInitializationProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('initialization-progress', (_, progress) => callback(progress))
  },
  removeInitializationProgressListener: () => {
    ipcRenderer.removeAllListeners('initialization-progress')
  },

  // 监听后端状态
  onBackendStatus: (callback: (status: unknown) => void) => {
    ipcRenderer.on('backend-status', (_, status) => callback(status))
  },
  removeBackendStatusListener: () => {
    ipcRenderer.removeAllListeners('backend-status')
  },

  // 监听日志管理服务事件
  onLogManagementEvent: (callback: (event: string, data: unknown) => void) => {
    ipcRenderer.on('log-management-event', (_, event, data) => callback(event, data))
  },
  removeLogManagementEventListener: () => {
    ipcRenderer.removeAllListeners('log-management-event')
  },

  // 监听日志更新
  onLogUpdate: (callback: (logs: unknown[]) => void) => {
    ipcRenderer.on('log-update', (_, logs) => callback(logs))
  },
  removeLogUpdateListener: () => {
    ipcRenderer.removeAllListeners('log-update')
  },

  // 监听日志统计更新
  onLogStatsUpdate: (callback: (stats: unknown) => void) => {
    ipcRenderer.on('log-stats-update', (_, stats) => callback(stats))
  },
  removeLogStatsUpdateListener: () => {
    ipcRenderer.removeAllListeners('log-stats-update')
  },
})
