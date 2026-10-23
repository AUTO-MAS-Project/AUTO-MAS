import { contextBridge, ipcRenderer } from 'electron'
import type { RendererAnalyticsEvent } from '../src/types/analytics'
import type { AppearanceCategory } from '../src/types/mascotPack'
import type {
  DesktopMascotColors,
  DesktopMascotIdleMessage,
  DesktopMascotMenuLabels,
  DesktopMascotMenuResult,
  DesktopMascotSelection,
  DesktopMascotTaskAction,
  DesktopMascotTaskMenu,
} from '../src/types/desktopMascot'

window.addEventListener('DOMContentLoaded', () => {
  // 预加载脚本已加载
})

// 暴露安全的 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  analytics: {
    getContext: () => ipcRenderer.invoke('analytics:context'),
    trackEvent: (context: number, event: RendererAnalyticsEvent) =>
      ipcRenderer.send('analytics:event', context, event),
  },
  isMacOS: process.platform === 'darwin',
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
  onWindowMaximizedChange: (callback: (maximized: boolean) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, maximized: boolean) => callback(maximized)
    ipcRenderer.on('window-maximized-changed', listener)
    return () => ipcRenderer.removeListener('window-maximized-changed', listener)
  },
  windowFocus: () => ipcRenderer.invoke('window-focus'),
  setDesktopMascotReady: (
    ready: boolean,
    labels?: DesktopMascotMenuLabels,
    colors?: DesktopMascotColors
  ) => ipcRenderer.invoke('desktop-mascot:ready', ready, labels, colors),
  setDesktopMascotActivity: (working: boolean, animate: boolean) =>
    ipcRenderer.invoke('desktop-mascot:activity', working, animate),
  setDesktopMascotIdleMessage: (message: DesktopMascotIdleMessage) =>
    ipcRenderer.invoke('desktop-mascot:idle-message', message),
  showDesktopMascotNotice: (
    text: string,
    reaction?: 'success' | 'failure' | 'stopped',
    key?: string
  ) => ipcRenderer.invoke('desktop-mascot:notice', text, reaction, key),
  onDesktopMascotError: (callback: () => void) => {
    const listener = () => callback()
    ipcRenderer.on('desktop-mascot:error', listener)
    return () => ipcRenderer.removeListener('desktop-mascot:error', listener)
  },
  onDesktopMascotRefreshIdleMessage: (callback: () => void) => {
    const listener = () => callback()
    ipcRenderer.on('desktop-mascot:refresh-idle-message', listener)
    return () => ipcRenderer.removeListener('desktop-mascot:refresh-idle-message', listener)
  },
  onDesktopMascotTaskMenuRequest: (callback: (requestId: number) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, requestId: number) => callback(requestId)
    ipcRenderer.on('desktop-mascot:task-menu-request', listener)
    return () => ipcRenderer.removeListener('desktop-mascot:task-menu-request', listener)
  },
  setDesktopMascotTaskMenu: (requestId: number, menu: DesktopMascotTaskMenu) =>
    ipcRenderer.invoke('desktop-mascot:task-menu', requestId, menu),
  onDesktopMascotTaskMenuClosed: (callback: (requestId: number) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, requestId: number) => callback(requestId)
    ipcRenderer.on('desktop-mascot:task-menu-closed', listener)
    return () => ipcRenderer.removeListener('desktop-mascot:task-menu-closed', listener)
  },
  onDesktopMascotTaskAction: (
    callback: (action: DesktopMascotTaskAction, requestId: number) => void
  ) => {
    const listener = (
      _event: Electron.IpcRendererEvent,
      action: DesktopMascotTaskAction,
      requestId: number
    ) => callback(action, requestId)
    ipcRenderer.on('desktop-mascot:task-action', listener)
    return () => ipcRenderer.removeListener('desktop-mascot:task-action', listener)
  },
  setDesktopMascotTaskActionResult: (requestId: number, result: DesktopMascotMenuResult) =>
    ipcRenderer.invoke('desktop-mascot:task-action-result', requestId, result),
  // 电源操作倒计时警示：主进程负责把窗口拉到最前并临时置顶
  powerWarningStart: () => ipcRenderer.invoke('power-warning:start'),
  powerWarningEnd: () => ipcRenderer.invoke('power-warning:end'),
  appQuit: () => ipcRenderer.invoke('app-quit'),
  appWaitForQuitConfirmation: () => ipcRenderer.invoke('app-wait-for-quit-confirmation'),
  appPrepareQuit: () => ipcRenderer.invoke('app-prepare-quit'),
  appConfirmQuit: (token: number) => ipcRenderer.invoke('app-confirm-quit', token),
  appCancelQuit: (token?: number) => ipcRenderer.invoke('app-cancel-quit', token),
  appRestart: () => ipcRenderer.invoke('app-restart'),
  appRestartOnQuit: () => ipcRenderer.invoke('app-restart-on-quit'),

  // 系统休眠恢复与主进程关闭请求（生命周期协调器消费）
  onSystemResume: (callback: () => void) => {
    const listener = () => callback()
    ipcRenderer.on('system-resumed', listener)
    return () => ipcRenderer.removeListener('system-resumed', listener)
  },
  onAppCloseRequested: (callback: (confirmRunningTasks: boolean) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, confirmRunningTasks: boolean) =>
      callback(confirmRunningTasks)
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
  saveConfig: (config: unknown, defaults?: unknown) =>
    ipcRenderer.invoke('save-config', config, defaults),
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
  exportLogs: (dialogLabels?: { title: string; zipFilterName: string }) =>
    ipcRenderer.invoke('log:export', dialogLabels),
  exportMaaIssueReport: (dialogLabels?: { title: string; zipFilterName: string }) =>
    ipcRenderer.invoke('maa:exportIssueReport', undefined, dialogLabels),
  exportMaaEndIssueReport: () => ipcRenderer.invoke('maaend:exportIssueReport'),
  exportOkwwIssueReport: () => ipcRenderer.invoke('okww:exportIssueReport'),
  exportOkNteIssueReport: () => ipcRenderer.invoke('oknte:exportIssueReport'),
  exportZzzOdIssueReport: () => ipcRenderer.invoke('zzzod:exportIssueReport'),
  exportWhimboxIssueReport: () => ipcRenderer.invoke('whimbox:exportIssueReport'),
  exportBetterGIIssueReport: () => ipcRenderer.invoke('bettergi:exportIssueReport'),
  listMaaFWIssueReportScripts: (configTypes: string[]) =>
    ipcRenderer.invoke('maafw:listIssueReportScripts', configTypes),
  exportMaaFWIssueReport: (scriptId: string) =>
    ipcRenderer.invoke('maafw:exportIssueReport', scriptId),
  exportM9AIssueReport: () => ipcRenderer.invoke('m9a:exportIssueReport'),
  exportMSSIssueReport: () => ipcRenderer.invoke('mss:exportIssueReport'),
  exportDataBackup: () => ipcRenderer.invoke('data:backup'),
  // 传 fromOffset 时只读该字节偏移之后的新增部分，返回 { content, size, reset }
  getLogs: (lines?: number, fileName?: string, fromOffset?: number) =>
    ipcRenderer.invoke('log:getContent', lines, fileName, fromOffset),
  openLogWindow: (file?: 'app' | 'frontend') => ipcRenderer.invoke('log:openWindow', file),

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
  readFileBase64: (filePath: string, maxBytes?: number) =>
    ipcRenderer.invoke('read-file-base64', filePath, maxBytes),
  fileExists: (filePath: string) => ipcRenderer.invoke('file-exists', filePath),

  getAppPath: (name: string) => ipcRenderer.invoke('get-app-path', name),

  // 自定义外观包：主进程完成 ZIP 校验后只返回已声明素材的 data URL。
  listAppearances: () => ipcRenderer.invoke('appearance:list'),
  listMascots: () => ipcRenderer.invoke('mascot:list'),
  importMascot: (zipPath: string, replace = false) =>
    ipcRenderer.invoke('mascot:import', zipPath, replace),
  removeMascot: (id: string) => ipcRenderer.invoke('mascot:remove', id),
  onMascotChanged: (callback: (selection?: DesktopMascotSelection) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, selection?: DesktopMascotSelection) =>
      callback(selection)
    ipcRenderer.on('mascot-changed', listener)
    return () => ipcRenderer.removeListener('mascot-changed', listener)
  },
  getAppearance: (id: string) => ipcRenderer.invoke('appearance:get', id),
  importAppearance: (zipPath: string, replace = false) =>
    ipcRenderer.invoke('appearance:import', zipPath, replace),
  removeAppearance: (id: string) => ipcRenderer.invoke('appearance:remove', id),
  clearInvalidAppearance: (expectedId: string) =>
    ipcRenderer.invoke('appearance:clear-invalid', expectedId),
  // 在线外观：下载、校验与安装都在主进程完成，渲染进程只拿 token。
  listOnlineAppearances: (
    query?: { page?: number; pageSize?: number; keyword?: string },
    category?: AppearanceCategory
  ) => ipcRenderer.invoke('appearance:online-list', query, category),
  getOnlineAppearance: (fileKey: string, category?: AppearanceCategory) =>
    ipcRenderer.invoke('appearance:online-detail', fileKey, category),
  prepareOnlineAppearance: (fileKey: string, versionNo: number, category?: AppearanceCategory) =>
    ipcRenderer.invoke('appearance:online-prepare', fileKey, versionNo, category),
  installOnlineAppearance: (token: string, replace = false, category?: AppearanceCategory) =>
    ipcRenderer.invoke('appearance:online-install', token, replace, category),
  discardOnlineAppearance: (token: string, category?: AppearanceCategory) =>
    ipcRenderer.invoke('appearance:online-discard', token, category),
  getOnlineAppearanceCover: (fileKey: string, versionNo?: number, category?: AppearanceCategory) =>
    ipcRenderer.invoke('appearance:online-cover', fileKey, versionNo, category),
  inspectLocalAppearance: (zipPath: string, category?: AppearanceCategory) =>
    ipcRenderer.invoke('appearance:inspect-local', zipPath, category),
  inspectAppearanceCover: (imagePath: string) =>
    ipcRenderer.invoke('appearance:inspect-cover', imagePath),
  onAppearanceChanged: (callback: () => void) => {
    const listener = () => callback()
    ipcRenderer.on('appearance-changed', listener)
    return () => ipcRenderer.removeListener('appearance-changed', listener)
  },
  onThemeConfigChanged: (callback: (config: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, config: unknown) => callback(config)
    ipcRenderer.on('theme-config-changed', listener)
    return () => ipcRenderer.removeListener('theme-config-changed', listener)
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
  checkRuntimeBinaryUpdate: () => ipcRenderer.invoke('check-runtime-binary-update'),
  updateRuntimeBinary: () => ipcRenderer.invoke('update-runtime-binary'),
  onRuntimeBinaryProgress: (callback: (progress: unknown) => void) => {
    ipcRenderer.on('runtime-binary-progress', (_, progress) => callback(progress))
  },
  removeRuntimeBinaryProgressListener: () => {
    ipcRenderer.removeAllListeners('runtime-binary-progress')
  },

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
