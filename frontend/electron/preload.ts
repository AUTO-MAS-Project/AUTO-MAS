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
  checkCriticalFiles: () => ipcRenderer.invoke('check-critical-files'),

  // 后端管理
  startBackend: () => ipcRenderer.invoke('backend-start'),
  stopBackend: () => ipcRenderer.invoke('backend-stop'),

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
  updateTraySettings: (uiSettings: unknown) =>
    ipcRenderer.invoke('update-tray-settings', uiSettings),

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
  exportZzzOdIssueReport: () => ipcRenderer.invoke('zzzod:exportIssueReport'),
  exportDataBackup: () => ipcRenderer.invoke('data:backup'),
  // 传 fromOffset 时只读该字节偏移之后的新增部分，返回 { content, size, reset }
  getLogs: (lines?: number, fileName?: string, fromOffset?: number) =>
    ipcRenderer.invoke('log:getContent', lines, fileName, fromOffset),
  openLogWindow: (file?: 'app' | 'frontend') => ipcRenderer.invoke('log:openWindow', file),
  openBettergiScriptRepoWindow: (scriptId: string) =>
    ipcRenderer.invoke('bettergi-script-repo:openWindow', scriptId),

  // 虚拟显示器询问弹窗：主窗口把后端消息转给主进程开窗；弹窗页面自己取数据、自己关
  showVirtualDisplayPrompt: (payload: unknown) => ipcRenderer.invoke('vdd-prompt:show', payload),
  closeVirtualDisplayPrompt: () => ipcRenderer.invoke('vdd-prompt:close'),
  getVirtualDisplayPrompt: () => ipcRenderer.invoke('vdd-prompt:get'),
  onVirtualDisplayPromptData: (callback: (payload: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, payload: unknown) => callback(payload)
    ipcRenderer.on('vdd-prompt:data', listener)
    return () => ipcRenderer.removeListener('vdd-prompt:data', listener)
  },

  // 日志窗已经开着时主进程不会重新载入，改由主进程推送要看的那一份
  onLogSelectFile: (callback: (file: 'app' | 'frontend') => void) => {
    ipcRenderer.on('log:selectFile', (_, file) => callback(file))
  },
  removeLogSelectFileListener: () => {
    ipcRenderer.removeAllListeners('log:selectFile')
  },

  // 获取模块化日志器（使用 electron-log）
  getLogger: (moduleName: string) => ({
    debug: (...args: unknown[]) => ipcRenderer.invoke('log:write', 'debug', moduleName, ...args),
    info: (...args: unknown[]) => ipcRenderer.invoke('log:write', 'info', moduleName, ...args),
    warn: (...args: unknown[]) => ipcRenderer.invoke('log:write', 'warn', moduleName, ...args),
    error: (...args: unknown[]) => ipcRenderer.invoke('log:write', 'error', moduleName, ...args),
  }),

  // 文件系统操作
  openFile: (filePath: string) => ipcRenderer.invoke('open-file', filePath),
  showItemInFolder: (filePath: string) => ipcRenderer.invoke('show-item-in-folder', filePath),
  readFile: (filePath: string) => ipcRenderer.invoke('read-file', filePath),
  fileExists: (filePath: string) => ipcRenderer.invoke('file-exists', filePath),

  getAppPath: (name: string) => ipcRenderer.invoke('get-app-path', name),

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

  // 完整初始化流程（Runtime 首次初始化与旧链路共用）
  initialize: (targetBranch?: string, startBackend?: boolean) =>
    ipcRenderer.invoke('initialize', targetBranch, startBackend),

  // 后端服务管理（startBackend/stopBackend 与 backendStart 两套命名都有渲染进程在用，先都保留）
  backendStart: () => ipcRenderer.invoke('backend-start'),
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
})
