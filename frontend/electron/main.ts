import {
  app,
  BrowserWindow,
  dialog,
  globalShortcut,
  ipcMain,
  Menu,
  type MenuItemConstructorOptions,
  nativeImage,
  nativeTheme,
  Notification,
  powerMonitor,
  screen,
  shell,
  Tray,
  type Display,
  type Rectangle,
} from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import { getAppRoot } from './services/environmentService'
import {
  registerInitializationHandlers,
  checkCriticalFilesViaRuntime,
  getBackendService,
  getLocalApiEndpoint,
  resolveRuntimeInitContext,
} from './ipc/initializationHandlers'
import { registerFileHandlers } from './ipc/fileHandlers'
import { registerOkwwPathDiscoveryHandlers } from './ipc/okwwPathDiscoveryHandlers'
import {
  canElectronExitImmediately,
  canRequestRendererClose,
  markForceQuitFailed,
} from './quitCoordinationState'
import { decideRendererRecovery } from './rendererCrashRecovery'

import { getLogger, initializeLogger } from './services/logger'
import { readLogContent, readLogIncrement } from './services/logFileReader'
import { createMaaEndIssueReport } from './services/maaEndIssueReportService'
import {
  createM9AIssueReport,
  createMaaFWIssueReport,
  listMaaFWIssueReportScripts,
  maafwIssueReportFileNamePrefix,
} from './services/maafwIssueReportService'
import { createOkwwIssueReport } from './services/okwwIssueReportService'
import { createOkNteIssueReport } from './services/okNteIssueReportService'
import { createZzzOdIssueReport } from './services/zzzOdIssueReportService'
import {
  captureMainRendererCrash,
  configureMainSentry,
  recordMainCount,
  recordMainStartup,
  setMainTelemetryEnabled,
} from './services/sentry'
import { applyInstanceIdentity, resolveStopAllTasksShortcut } from './services/instanceConfig'
import {
  PersistedRuntimeLaunchMode,
  isPersistedRuntimeLaunchMode,
  resolveRuntimeLaunchModeDetail,
} from './services/runtime'
import AdmZip = require('adm-zip')

// 开发环境切换到独立的 userData 目录（必须在 app ready 之前）
applyInstanceIdentity()

// 初始化日志系统（必须在创建 logger 之前）
initializeLogger()

const logger = getLogger('主进程')
const STOP_ALL_TASKS_SHORTCUT = resolveStopAllTasksShortcut()
let isStoppingAllTasks = false

interface ApiResult {
  code?: number
  message?: string
}

// 托盘菜单项类型
type TrayAction = 'show' | 'hide' | 'startTask' | 'stopAll' | 'restartApp' | 'quit'

interface TrayItem {
  id: string
  label: string
  action: TrayAction
  // 仅 action === 'startTask' 时有效：要启动的队列/脚本 ID
  taskId?: string
}

// 默认托盘菜单项（与旧版硬编码菜单保持一致）
const DEFAULT_TRAY_ITEMS: TrayItem[] = [
  { id: 'show', label: '显示窗口', action: 'show' },
  { id: 'hide', label: '隐藏窗口', action: 'hide' },
  { id: 'quit', label: '退出', action: 'quit' },
]

function showShortcutNotification(title: string, body: string): void {
  if (Notification.isSupported()) {
    new Notification({ title, body }).show()
  }
}

async function stopAllTasksByShortcut(): Promise<void> {
  if (isStoppingAllTasks) {
    logger.info('全部任务正在停止中，忽略重复快捷键')
    return
  }

  isStoppingAllTasks = true
  logger.info(`触发全局快捷键 ${STOP_ALL_TASKS_SHORTCUT}，开始停止所有任务`)

  try {
    const apiUrl = `${getLocalApiEndpoint()}/api/dispatch/stop`
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ taskId: 'ALL' }),
    })

    if (!response.ok) {
      throw new Error(`停止请求返回错误: ${response.status}`)
    }

    const result = (await response.json()) as ApiResult
    if (result.code !== undefined && result.code !== 200) {
      throw new Error(result.message || `停止请求失败: ${result.code}`)
    }

    logger.info('所有任务已停止')
    showShortcutNotification('AUTO-MAS', '所有任务已停止')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`全局快捷键停止所有任务失败: ${errorMsg}`)
    showShortcutNotification('AUTO-MAS', `停止所有任务失败: ${errorMsg}`)
  } finally {
    isStoppingAllTasks = false
  }
}

function registerStopAllTasksShortcut(): void {
  const registered = globalShortcut.register(STOP_ALL_TASKS_SHORTCUT, () => {
    void stopAllTasksByShortcut()
  })

  if (registered) {
    logger.info(`全局停止任务快捷键已注册: ${STOP_ALL_TASKS_SHORTCUT}`)
  } else {
    logger.error(`全局停止任务快捷键注册失败: ${STOP_ALL_TASKS_SHORTCUT}`)
  }
}

let forceKillPromise: Promise<void> | null = null

// 强制清理也通过唯一 BackendService 队列执行，避免与 start/stop/restart 并发。
// 仅限定范围强杀本应用相关进程，绝不使用 taskkill /im python.exe 全量误杀。
async function forceKillRelatedProcesses(): Promise<void> {
  if (forceKillPromise) return forceKillPromise
  forceKillPromise = (async () => {
    const backendService = getBackendService()

    // Runtime 监督链路：只向监督进程发 shutdown（有上限，超时才 kill Runtime 进程本身），
    // 后端进程树由 Runtime 的 Job Object 收走，不再走 processManager 的全局清理。
    if (backendService.isRuntimeSupervised()) {
      const result = await backendService.stopBackend()
      if (!result.success) throw new Error(result.error || '未知错误')
      logger.info('Runtime 监督的后端已关闭')
      return
    }

    const result = await backendService.forceStopBackend()
    if (!result.success) throw new Error(result.error || '未知错误')
    logger.info('所有相关进程已清理')
  })().finally(() => {
    forceKillPromise = null
  })
  return forceKillPromise
}

// 检查是否以管理员权限运行
function isRunningAsAdmin(): boolean {
  try {
    // 在Windows上，尝试写入系统目录来检查管理员权限
    if (process.platform === 'win32') {
      const testPath = path.join(process.env.WINDIR || 'C:\\Windows', 'temp', 'admin-test.tmp')
      try {
        fs.writeFileSync(testPath, 'test')
        fs.unlinkSync(testPath)
        return true
      } catch {
        return false
      }
    }
    return true // 非Windows系统暂时返回true
  } catch {
    return false
  }
}

let tray: Tray | null = null
let coordinatedQuit = false
let forceQuitInProgress = false
let quitRequestInFlight = false
let relaunchAfterQuit = false
let quitFallbackTimer: NodeJS.Timeout | null = null
const RENDERER_QUIT_FALLBACK_MS = 25000
let saveWindowStateTimeout: NodeJS.Timeout | null = null
let rendererCrashes: number[] = []
let isInitialStartup = true // 标记是否为初次启动
const isAutoStart = process.argv.includes('--auto-start') // 是否由开机自启动任务计划拉起

// 配置接口
interface AppConfig {
  UI: {
    IfShowTray: boolean
    IfToTray: boolean
    IfHideCloseButton: boolean
    location: string
    maximized: boolean
    size: string
    TrayItems?: TrayItem[]
  }
  Start: {
    IfMinimizeDirectly: boolean
    IfSelfStart: boolean
  }
  Update: {
    IfAutoUpdate: boolean
  }
  Function: {
    IfEnableTelemetry: boolean
  }
  // Runtime 灰度开关的持久化设置，见 services/runtime/launchConfig.ts 的三级优先级说明。
  Runtime: {
    LaunchMode: PersistedRuntimeLaunchMode
  }

  [key: string]: unknown
}

// 默认配置
const defaultConfig: AppConfig = {
  UI: {
    IfShowTray: false,
    IfToTray: false,
    IfHideCloseButton: false,
    location: '100,100',
    maximized: false,
    size: '1600,1000',
  },
  Start: {
    IfMinimizeDirectly: false,
    IfSelfStart: false,
  },
  Update: {
    IfAutoUpdate: false,
  },
  Function: {
    IfEnableTelemetry: true,
  },
  Runtime: {
    LaunchMode: 'auto',
  },
}

//加载配置
function loadConfig(): AppConfig {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')
    let config = { ...defaultConfig }

    if (fs.existsSync(configPath)) {
      const configData = fs.readFileSync(configPath, 'utf8')
      config = { ...config, ...JSON.parse(configData) }
    }

    const backendConfigPath = path.join(appRoot, 'config', 'Config.json')
    if (fs.existsSync(backendConfigPath)) {
      const backendConfig = JSON.parse(fs.readFileSync(backendConfigPath, 'utf8'))
      const enabled = backendConfig.Function?.IfEnableTelemetry
      if (typeof enabled === 'boolean') {
        config.Function = { ...config.Function, IfEnableTelemetry: enabled }
      }
    }
    return config
  } catch {
    logger.error('加载配置失败')
  }
  return defaultConfig
}

// 保存配置
function saveConfig(config: AppConfig) {
  try {
    const appRoot = getAppRoot()
    const configDir = path.join(appRoot, 'config')
    const configPath = path.join(configDir, 'frontend_config.json')

    if (!fs.existsSync(configDir)) {
      fs.mkdirSync(configDir, { recursive: true })
    }

    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8')
  } catch {
    logger.error('保存配置失败')
  }
}

configureMainSentry(loadConfig().Function?.IfEnableTelemetry !== false)

// 创建托盘
function createTray() {
  if (tray) return

  // 尝试多个可能的图标路径
  const iconPaths = [
    path.join(__dirname, '../public/AUTO-MAS.ico'),
    path.join(process.resourcesPath, 'assets/AUTO-MAS.ico'),
    path.join(app.getAppPath(), 'public/AUTO-MAS.ico'),
    path.join(app.getAppPath(), 'dist/AUTO-MAS.ico'),
  ]

  let trayIcon

  try {
    // 尝试加载图标
    for (const iconPath of iconPaths) {
      if (fs.existsSync(iconPath)) {
        trayIcon = nativeImage.createFromPath(iconPath)
        if (!trayIcon.isEmpty()) {
          logger.info(`成功加载托盘图标: ${iconPath}`)
          break
        }
      }
    }

    // 如果所有路径都失败，创建一个默认图标
    if (!trayIcon || trayIcon.isEmpty()) {
      logger.warn('无法加载托盘图标，使用默认图标')
      trayIcon = nativeImage.createEmpty()
    }
  } catch {
    logger.error('加载托盘图标失败')
    trayIcon = nativeImage.createEmpty()
  }

  tray = new Tray(trayIcon)
  tray.setToolTip('AUTO-MAS')

  // 从配置读取托盘菜单项，未配置时回落到默认菜单
  const currentConfig = loadConfig()
  const trayItems = currentConfig.UI.TrayItems
  const items = trayItems?.length ? trayItems : DEFAULT_TRAY_ITEMS
  rebuildTrayMenu(items)

  // 双击托盘图标显示/隐藏窗口
  tray.on('double-click', () => {
    if (!mainWindow) return
    if (mainWindow.isVisible()) {
      hideMainWindow()
    } else {
      showMainWindow()
    }
  })
}

// 显示主窗口
function showMainWindow(): void {
  if (!mainWindow) return
  if (mainWindow.isMinimized()) {
    mainWindow.restore()
  }
  mainWindow.setSkipTaskbar(false) // 恢复任务栏图标
  mainWindow.show()
  mainWindow.focus()
}

// 隐藏主窗口
function hideMainWindow(): void {
  if (!mainWindow) return
  const currentConfig = loadConfig()
  if (currentConfig.UI.IfToTray) {
    mainWindow.setSkipTaskbar(true) // 隐藏任务栏图标
  }
  mainWindow.hide()
}

// 重建托盘右键菜单
function rebuildTrayMenu(items: TrayItem[]): void {
  if (!tray) return

  // 空列表时回落到默认菜单，避免托盘右键菜单为空
  const effectiveItems = items.length ? items : DEFAULT_TRAY_ITEMS

  const menuItems: MenuItemConstructorOptions[] = []
  effectiveItems.forEach((item, index) => {
    // 在「退出」前插入分隔线，保持与旧版菜单一致的视觉区分
    if (item.action === 'quit' && index > 0) {
      menuItems.push({ type: 'separator' })
    }
    menuItems.push({
      label: item.label,
      click: () => handleTrayAction(item),
    })
  })

  tray.setContextMenu(Menu.buildFromTemplate(menuItems))
}

// 执行托盘菜单项动作
function handleTrayAction(item: TrayItem): void {
  switch (item.action) {
    case 'show':
      showMainWindow()
      break
    case 'hide':
      hideMainWindow()
      break
    case 'stopAll':
      void stopAllTasksByShortcut()
      break
    case 'startTask':
      // 一键启动指定任务：需携带任务 ID 转发给渲染进程，由调度台新建任务并启动
      if (item.taskId) {
        requestTrayAction('startTask', item.taskId, item.label)
      } else {
        logger.warn('托盘启动任务缺少 taskId，忽略')
      }
      break
    case 'restartApp':
    case 'quit':
      // 退出/重启转发给渲染进程，与窗口关闭按钮走同一套确认流程
      requestTrayAction(item.action === 'restartApp' ? 'restart' : 'quit')
      break
  }
}

// 请求渲染进程处理托盘动作：启动需读取任务 ID 新建调度台，退出/重启由渲染进程按运行状态弹统一确认窗
function requestTrayAction(
  action: 'quit' | 'restart' | 'startTask',
  taskId?: string,
  label?: string
): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('tray-action-request', { action, taskId, label })
  } else {
    // 无主窗口时无法弹确认窗/新建调度台，仅退出与重启可直接执行；
    // renderer 不可用时 requestRendererClose 自动落入最终强杀兜底
    logger.warn('无主窗口，无法处理托盘动作，仅可执行退出/重启')
    if (action === 'restart') {
      relaunchAfterQuit = true
      requestRendererClose('托盘重启（无主窗口）')
    } else if (action === 'quit') {
      requestRendererClose('托盘退出（无主窗口）')
    }
    // startTask 依赖渲染进程新建调度台，无窗口时忽略
  }
}

// 销毁托盘
function destroyTray() {
  if (tray) {
    tray.destroy()
    tray = null
  }
}

// ==================== 协调退出 ====================

function clearQuitFallback(): void {
  if (quitFallbackTimer) {
    clearTimeout(quitFallbackTimer)
    quitFallbackTimer = null
  }
}

function finishCoordinatedQuit(): void {
  if (coordinatedQuit) return
  coordinatedQuit = true
  quitRequestInFlight = false
  clearQuitFallback()
  if (saveWindowStateTimeout) {
    clearTimeout(saveWindowStateTimeout)
    saveWindowStateTimeout = null
  }
  destroyTray()
  if (relaunchAfterQuit) app.relaunch()
  app.quit()
}

async function shouldPreserveBackendForDevMode(): Promise<boolean> {
  // 受 Runtime 监督的后端归 Runtime 生命周期管，即便是 development 模式也必须随之关闭，
  // 否则 Electron 退出后会遗留一个没人负责的监督进程。
  if (getBackendService().isRuntimeSupervised()) return false

  const backendDevMode = await getBackendService().getBackendDevMode()
  if (backendDevMode !== null) return backendDevMode
  return Boolean(process.env.VITE_DEV_SERVER_URL) || !app.isPackaged
}

async function forceQuitAfterRendererTimeout(reason: string): Promise<void> {
  if (forceQuitInProgress || coordinatedQuit) return
  forceQuitInProgress = true
  clearQuitFallback()
  logger.error(`renderer 未完成协调退出，执行最终强制清理: ${reason}`)

  // Electron 开发进程可能复用由开发者单独启动的后端；renderer 失联时也不能误杀。
  if (await shouldPreserveBackendForDevMode()) {
    logger.info('开发模式最终兜底：保留后端，仅关闭 Electron 前端')
    finishCoordinatedQuit()
    return
  }

  try {
    await forceKillRelatedProcesses()
    // forceStopBackend 只有在 scoped taskkill 已复查全部 PID 后才返回 success。
    finishCoordinatedQuit()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`最终强制清理失败: ${errorMsg}`)
    const retryableState = markForceQuitFailed({
      coordinatedQuit,
      forceQuitInProgress,
      quitRequestInFlight,
      relaunchAfterQuit,
    })
    forceQuitInProgress = retryableState.forceQuitInProgress
    quitRequestInFlight = retryableState.quitRequestInFlight
    relaunchAfterQuit = retryableState.relaunchAfterQuit
    if (mainWindow && !mainWindow.isDestroyed()) {
      showMainWindow()
    } else if (app.isReady()) {
      try {
        createWindow()
      } catch (windowError) {
        const windowErrorMsg =
          windowError instanceof Error ? windowError.message : String(windowError)
        logger.error(`强制清理失败后重建窗口失败: ${windowErrorMsg}`)
      }
    }
    dialog.showErrorBox(
      'AUTO-MAS 无法安全退出',
      `未能确认后端进程已退出，前端将保持运行以避免遗留后台进程。\n\n${errorMsg}`
    )
  }
}

function requestRendererClose(reason: string): void {
  if (!canRequestRendererClose({ coordinatedQuit, forceQuitInProgress, quitRequestInFlight }))
    return
  const win = mainWindow
  if (!win || win.isDestroyed()) {
    void forceQuitAfterRendererTimeout(`${reason}（renderer 不可用）`)
    return
  }

  quitRequestInFlight = true
  // 先让用户看到窗口已经关闭，renderer 保留在后台继续完成后端清理。
  win.setSkipTaskbar(true)
  win.hide()
  logger.info(`请求 renderer 执行协调退出: ${reason}`)
  win.webContents.send('app-close-requested')
  quitFallbackTimer = setTimeout(() => {
    void forceQuitAfterRendererTimeout(`${reason}（等待 ${RENDERER_QUIT_FALLBACK_MS}ms 超时）`)
  }, RENDERER_QUIT_FALLBACK_MS)
}

// 更新托盘状态
function updateTrayVisibility(config: AppConfig) {
  // 根据需求逻辑判断是否应该显示托盘
  let shouldShowTray = false

  if (config.UI.IfShowTray && config.UI.IfToTray) {
    // 勾选常驻显示托盘和最小化到托盘，就一直展示托盘
    shouldShowTray = true
  } else if (config.UI.IfShowTray && !config.UI.IfToTray) {
    // 勾选常驻显示托盘但没有最小化到托盘，就一直展示托盘
    shouldShowTray = true
  } else if (!config.UI.IfShowTray && config.UI.IfToTray) {
    // 没有常驻显示托盘但勾选最小化到托盘，有窗口时就只有窗口，最小化后任务栏消失，只有托盘
    shouldShowTray = !mainWindow || !mainWindow.isVisible()
  } else {
    // 没有常驻显示托盘也没有最小化到托盘，托盘一直不展示
    shouldShowTray = false
  }

  // 特殊情况：如果没有窗口显示且没有托盘，强制显示托盘避免程序成为幽灵
  if (!shouldShowTray && (!mainWindow || !mainWindow.isVisible()) && !tray) {
    shouldShowTray = true
    logger.warn('防幽灵机制：强制显示托盘图标')
  }

  if (shouldShowTray && !tray) {
    createTray()
    logger.info('托盘图标已创建')
  } else if (!shouldShowTray && tray) {
    destroyTray()
    logger.info('托盘图标已销毁')
  }
}

let mainWindow: Electron.BrowserWindow | null = null
let logWindow: Electron.BrowserWindow | null = null
let virtualDisplayPromptWindow: Electron.BrowserWindow | null = null
/** 日志窗打开时选中的那一份：后端的 app.log 或主进程的 frontend.log。 */
type LogWindowFile = 'app' | 'frontend'
type WindowActivity = 'visible' | 'background'
let lastWindowActivity: WindowActivity | null = null

function notifyWindowActivity(activity: WindowActivity) {
  if (!mainWindow || mainWindow.isDestroyed() || lastWindowActivity === activity) {
    return
  }

  lastWindowActivity = activity
  mainWindow.webContents.send('window-activity-changed', activity)
}

const TITLE_BAR_HEIGHT = 32
const RECOVERY_DRAG_HANDLE_WIDTH = 64

function findDisplayWithUsableTitleBar(bounds: Rectangle): Display | undefined {
  const handleWidth = Math.min(RECOVERY_DRAG_HANDLE_WIDTH, bounds.width)
  const handleHeight = Math.min(TITLE_BAR_HEIGHT, bounds.height)

  return screen.getAllDisplays().find(display => {
    const workArea = display.workArea

    return (
      bounds.x >= workArea.x &&
      bounds.y >= workArea.y &&
      bounds.x + handleWidth <= workArea.x + workArea.width &&
      bounds.y + handleHeight <= workArea.y + workArea.height
    )
  })
}

function centerBoundsInWorkArea(bounds: Rectangle, workArea: Rectangle): Rectangle {
  const width = Math.min(bounds.width, workArea.width)
  const height = Math.min(bounds.height, workArea.height)

  return {
    x: workArea.x + Math.floor((workArea.width - width) / 2),
    y: workArea.y + Math.floor((workArea.height - height) / 2),
    width,
    height,
  }
}

function parseConfigInteger(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value?.trim() ?? '', 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

/**
 * 开发环境的不变式：前端必须由 vite 开发服务器提供。
 *
 * 在加载前端**之前**先校验，而不是等加载失败再兜底——否则一旦
 * VITE_DEV_SERVER_URL 缺失，加载逻辑会静默回退去读 dist/，让开发者
 * 以为跑的是当前源码。开发环境下任何异常都应优先指出，不能静默换一条路。
 *
 * 打包分发不受影响（由 vite 产出的静态资源在 dist/ 中，正常读取）。
 */
function assertDevelopmentRuntime(): void {
  if (app.isPackaged) return
  if (process.env.VITE_DEV_SERVER_URL) return

  const message =
    '开发环境未设置 VITE_DEV_SERVER_URL：前端必须由 vite 开发服务器提供，' +
    '不会回退读取 dist/ 中的构建产物。\n\n' +
    '请使用 yarn dev 启动（会同时拉起 vite 与 electron）。'
  logger.error(message)
  dialog.showErrorBox('AUTO-MAS 开发环境启动方式不正确', message)
  app.quit()
  process.exit(1)
}

function createWindow() {
  logger.info('开始创建主窗口')

  const config = loadConfig()

  // 解析配置
  const [rawW, rawH] = (config.UI.size ?? defaultConfig.UI.size).split(',')
  const [rawX, rawY] = (config.UI.location ?? defaultConfig.UI.location).split(',')
  const parsedW = parseConfigInteger(rawW, 1600)
  const parsedH = parseConfigInteger(rawH, 1000)
  const cfgW = parsedW > 0 ? parsedW : 1600
  const cfgH = parsedH > 0 ? parsedH : 1000
  const cfgX = parseConfigInteger(rawX, 100)
  const cfgY = parseConfigInteger(rawY, 100)

  const savedBounds = { x: cfgX, y: cfgY, width: cfgW, height: cfgH }
  const savedDisplay = findDisplayWithUsableTitleBar(savedBounds)
  const targetDisplay = savedDisplay ?? screen.getPrimaryDisplay()
  const sf = targetDisplay.scaleFactor

  const { width: waW, height: waH } = targetDisplay.workArea

  // 逻辑最小尺寸（DIP）
  const minDipW = Math.min(Math.floor(960 / sf), waW)
  const minDipH = Math.min(Math.floor(900 / sf), waH)

  // 初始窗口逻辑尺寸（DIP）
  let initW = Math.max(cfgW, minDipW)
  let initH = Math.max(cfgH, minDipH)

  // 不超过工作区
  initW = Math.min(initW, waW)
  initH = Math.min(initH, waH)

  const candidateBounds = { x: cfgX, y: cfgY, width: initW, height: initH }
  const candidateDisplay = findDisplayWithUsableTitleBar(candidateBounds)
  const initialBounds = candidateDisplay
    ? candidateBounds
    : centerBoundsInWorkArea(candidateBounds, screen.getPrimaryDisplay().workArea)
  const boundsWereAdjusted =
    initialBounds.x !== savedBounds.x ||
    initialBounds.y !== savedBounds.y ||
    initialBounds.width !== savedBounds.width ||
    initialBounds.height !== savedBounds.height

  if (boundsWereAdjusted) {
    config.UI.size = `${initialBounds.width},${initialBounds.height}`
    config.UI.location = `${initialBounds.x},${initialBounds.y}`
    saveConfig(config)
    logger.warn('保存的窗口边界已调整到当前显示器的可见区域')
  }

  // 关键：用局部常量 win，全程用它，类型不为 null
  const win = new BrowserWindow({
    x: initialBounds.x,
    y: initialBounds.y,
    width: initialBounds.width,
    height: initialBounds.height,
    minWidth: minDipW,
    minHeight: minDipH,
    useContentSize: true,
    frame: false,
    titleBarStyle: 'hidden',
    icon: path.join(__dirname, '../public/AUTO-MAS.ico'),
    autoHideMenuBar: true,
    show: false, // 改为 false，等待页面加载完成后再显示
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#000000' : '#ffffff', // 根据系统主题设置背景色
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      backgroundThrottling: false, // 防止后台节流
    },
  })

  // 把局部的 win 赋值给模块级（供其他模块/函数用）
  mainWindow = win
  lastWindowActivity = null

  // 崩溃时窗口若在托盘里，恢复后保持隐藏，不要自己弹出来打断用户。
  let keepHiddenAfterRecovery = false

  // 渲染进程崩溃恢复。Electron 不会自动重建崩掉的渲染进程：BrowserWindow 还在，
  // 托盘和显示/隐藏都正常，但里面的 frame 已经没了，用户看到的是一个永远黑着的
  // 窗口，只能从任务管理器强杀。没有这个监听时日志里也不会留下任何记录。
  win.webContents.on('render-process-gone', (_event, details) => {
    const decision = decideRendererRecovery({
      reason: details.reason,
      exitCode: details.exitCode,
      isQuitting: coordinatedQuit || forceQuitInProgress || quitRequestInFlight,
      isWindowDestroyed: win.isDestroyed(),
      now: Date.now(),
      previousCrashes: rendererCrashes,
    })
    rendererCrashes = decision.crashes

    if (decision.action === 'ignore') {
      logger.info(decision.detail)
      return
    }

    logger.error(decision.detail)
    captureMainRendererCrash({
      reason: details.reason,
      exitCode: details.exitCode,
      crashCount: decision.crashCount,
      action: decision.action,
      detail: decision.detail,
    })

    if (decision.action === 'give-up') return

    keepHiddenAfterRecovery = !win.isVisible()
    win.webContents.reload()
  })

  win.on('unresponsive', () => {
    logger.warn('渲染进程无响应（主线程卡住），等待其自行恢复')
    recordMainCount('auto_mas.app.renderer.unresponsive', { component: 'electron-main' })
  })

  win.on('responsive', () => {
    logger.info('渲染进程已恢复响应')
  })

  // Electron 在最大化窗口最小化后会让 isMaximized() 返回 false，单独记住恢复目标状态。
  let restoreToMaximized = Boolean(config.UI.maximized)
  win.on('maximize', () => {
    restoreToMaximized = true
  })
  win.on('unmaximize', () => {
    restoreToMaximized = false
  })
  win.on('restore', () => {
    notifyWindowActivity('visible')
    if (restoreToMaximized && !win.isMaximized()) {
      win.maximize()
    }
  })

  // 页面加载完成后再显示窗口，避免白屏闪烁
  win.webContents.on('did-finish-load', () => {
    // 崩溃前窗口就在托盘里，恢复后保持隐藏，不要打断用户。
    if (keepHiddenAfterRecovery) {
      keepHiddenAfterRecovery = false
      notifyWindowActivity('background')
      logger.info('渲染进程已恢复，窗口保持托盘隐藏状态')
      return
    }

    // 仅开机自启动且开启"启动后直接最小化"时才隐藏窗口，手动双击启动始终显示
    if (!(isAutoStart && config.Start.IfMinimizeDirectly)) {
      win.show()
      logger.info('页面加载完成，窗口已显示')
    } else {
      notifyWindowActivity('background')
      logger.info('页面加载完成，窗口保持后台状态')
    }
  })

  // 根据显示器动态更新最小尺寸/边界
  const recomputeMinSize = () => {
    // 这里用 win，不会是 null
    const isMinimized = win.isMinimized()
    const bounds = isMinimized ? win.getNormalBounds() : win.getBounds()
    const disp = screen.getDisplayMatching(bounds)
    const s = disp.scaleFactor
    const w = Math.min(Math.floor(960 / s), disp.workArea.width)
    const h = Math.min(Math.floor(900 / s), disp.workArea.height)

    const [curMinW, curMinH] = win.getMinimumSize()
    if (w !== curMinW || h !== curMinH) {
      win.setMinimumSize(w, h)
    }

    if (win.isMaximized() || isMinimized) return

    const { width: wW, height: wH } = disp.workArea
    const newBounds = { ...bounds }
    if (newBounds.width > wW) newBounds.width = wW
    if (newBounds.height > wH) newBounds.height = wH
    if (newBounds.width < w) newBounds.width = w
    if (newBounds.height < h) newBounds.height = h

    if (newBounds.width !== bounds.width || newBounds.height !== bounds.height) {
      win.setBounds(newBounds)
    }
  }

  const ensureWindowIsVisible = () => {
    if (win.isDestroyed()) return

    const wasMinimized = win.isMinimized()
    const wasVisible = win.isVisible()
    const wasMaximized = win.isMaximized() || (!wasVisible && restoreToMaximized)
    const bounds = wasMaximized || wasMinimized ? win.getNormalBounds() : win.getBounds()
    if (findDisplayWithUsableTitleBar(bounds)) return

    const safeBounds = centerBoundsInWorkArea(bounds, screen.getPrimaryDisplay().workArea)

    if (!wasMinimized && wasMaximized) win.unmaximize()
    win.setBounds(safeBounds)
    if (!wasMinimized && wasMaximized) {
      if (wasVisible) {
        win.maximize()
      } else {
        restoreToMaximized = true
      }
    }

    const currentConfig = loadConfig()
    currentConfig.UI.size = `${safeBounds.width},${safeBounds.height}`
    currentConfig.UI.location = `${safeBounds.x},${safeBounds.y}`
    currentConfig.UI.maximized = wasMaximized
    saveConfig(currentConfig)
    logger.warn('显示器布局发生变化，窗口已恢复到主显示器中央')
  }

  const handleDisplayConfigurationChanged = () => {
    ensureWindowIsVisible()
    recomputeMinSize()
  }

  // 监听显示器变化/窗口移动
  win.on('moved', recomputeMinSize)
  win.on('resized', recomputeMinSize)
  screen.on('display-metrics-changed', handleDisplayConfigurationChanged)
  screen.on('display-removed', handleDisplayConfigurationChanged)

  // 最大化配置
  if (config.UI.maximized) {
    win.maximize()
  }

  win.setMenuBarVisibility(false)
  assertDevelopmentRuntime()
  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    logger.info(`加载开发服务器: ${devServer}`)
    win.loadURL(devServer)
  } else {
    const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
    logger.info(`加载生产环境页面: ${indexHtmlPath}`)
    win.loadFile(indexHtmlPath)
  }

  // 窗口事件处理
  win.on('close', (event: Electron.Event) => {
    const currentConfig = loadConfig()
    const quitState = { coordinatedQuit, forceQuitInProgress, quitRequestInFlight }

    if (!canElectronExitImmediately(quitState)) {
      event.preventDefault()
      if (forceQuitInProgress) {
        logger.warn('强制清理仍在进行，暂不允许窗口提前关闭')
        return
      }
      if (currentConfig.UI.IfToTray && !quitRequestInFlight) {
        win.hide()
        win.setSkipTaskbar(true)
        updateTrayVisibility(currentConfig)
        logger.info('窗口已最小化到托盘，任务栏图标已隐藏')
      } else {
        requestRendererClose('窗口关闭')
      }
    } else {
      // 仅在 renderer 已完成协调退出后允许真实关闭窗口，并立即保存窗口状态
      if (!win.isDestroyed()) {
        try {
          const config = loadConfig()
          const isMinimized = win.isMinimized()
          const bounds = isMinimized ? win.getNormalBounds() : win.getBounds()
          const isMaximized =
            !win.isVisible() || isMinimized ? restoreToMaximized : win.isMaximized()

          if (!isMaximized) {
            config.UI.size = `${bounds.width},${bounds.height}`
            config.UI.location = `${bounds.x},${bounds.y}`
          }
          config.UI.maximized = isMaximized

          saveConfig(config)
          logger.info('窗口状态已保存')
        } catch {
          logger.error('保存窗口状态失败')
        }
      }
    }
  })

  win.on('closed', () => {
    logger.info('主窗口已关闭')
    closeVirtualDisplayPrompt()
    // 清理监听（可选）
    screen.removeListener('display-metrics-changed', handleDisplayConfigurationChanged)
    screen.removeListener('display-removed', handleDisplayConfigurationChanged)
    // 置空模块级引用
    mainWindow = null
  })

  win.on('minimize', () => {
    notifyWindowActivity('background')
    const currentConfig = loadConfig()
    if (currentConfig.UI.IfToTray) {
      win.hide()
      win.setSkipTaskbar(true)
      updateTrayVisibility(currentConfig)
      logger.info('窗口已最小化到托盘，任务栏图标已隐藏')
    }
  })

  win.on('show', () => {
    notifyWindowActivity('visible')
    if (restoreToMaximized && !win.isMaximized() && !win.isMinimized()) {
      win.maximize()
    }
    const currentConfig = loadConfig()
    win.setSkipTaskbar(false)
    updateTrayVisibility(currentConfig)
    logger.info('窗口已显示，任务栏图标已恢复')
  })

  win.on('hide', () => {
    notifyWindowActivity('background')
    const currentConfig = loadConfig()
    if (currentConfig.UI.IfToTray) {
      win.setSkipTaskbar(true)
      logger.info('窗口已隐藏，任务栏图标已隐藏')
    }
    updateTrayVisibility(currentConfig)
  })

  // 窗口尺寸/位置变化时防抖保存
  const debounceSaveState = () => {
    if (saveWindowStateTimeout) {
      clearTimeout(saveWindowStateTimeout)
    }
    saveWindowStateTimeout = setTimeout(() => {
      if (win && !win.isDestroyed()) {
        try {
          const config = loadConfig()
          const isMinimized = win.isMinimized()
          const bounds = isMinimized ? win.getNormalBounds() : win.getBounds()
          const isMaximized =
            !win.isVisible() || isMinimized ? restoreToMaximized : win.isMaximized()

          if (!isMaximized) {
            config.UI.size = `${bounds.width},${bounds.height}`
            config.UI.location = `${bounds.x},${bounds.y}`
          }
          config.UI.maximized = isMaximized

          saveConfig(config)
          logger.info('窗口状态已自动保存')
        } catch {
          logger.error('保存窗口状态失败')
        }
      }
    }, 500)
  }

  win.on('resize', debounceSaveState)
  win.on('move', debounceSaveState)

  // 主窗口创建完成
  logger.info('主窗口创建完成')

  // 注册初始化处理器
  registerInitializationHandlers(win)
  logger.info('应用初始化处理器已注册')

  // 注册文件处理器
  registerFileHandlers()
  logger.info('文件处理器已注册')

  // 初始托盘配置（使用文件配置）
  updateTrayVisibility(config)

  // 等待窗口准备完成后再初始化托盘和处理启动配置
  win.webContents.once('did-finish-load', () => {
    recordMainStartup()

    // 重新加载配置以确保获取最新配置
    const currentConfig = loadConfig()

    // 根据配置初始化托盘
    updateTrayVisibility(currentConfig)

    // 处理启动后直接最小化（仅开机自启动时执行）
    if (isAutoStart && isInitialStartup && currentConfig.Start.IfMinimizeDirectly) {
      if (currentConfig.UI.IfToTray) {
        win.hide()
        win.setSkipTaskbar(true)
        logger.info('应用初次启动后直接最小化到托盘')
      } else {
        win.minimize()
        logger.info('应用初次启动后直接最小化')
      }
      updateTrayVisibility(currentConfig)
    }

    // 标记初次启动已完成
    isInitialStartup = false
  })
}

// 创建日志窗口
// file 指定落地时选中哪一份日志；启动/初始化路径要的是主进程写的 frontend.log，
// 因为那时后端还没起来，debug/app.log 不存在或者还停在上一轮。
function createLogWindow(file?: LogWindowFile) {
  // 如果日志窗口已存在，则切到请求的那一份再聚焦——只聚焦的话，之前停在后端日志的窗口
  // 会让「查看日志」看上去仍然没有内容，正是这次要修的现象。
  if (logWindow && !logWindow.isDestroyed()) {
    if (file) logWindow.webContents.send('log:selectFile', file)
    logWindow.focus()
    return
  }

  logger.info('创建日志窗口')

  logWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: '日志查看 - AUTO-MAS',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    autoHideMenuBar: true,
    show: false,
  })

  const hash = file ? `/logs?file=${file}` : '/logs'
  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    logWindow.loadURL(`${devServer}#${hash}`)
  } else {
    const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
    logWindow.loadFile(indexHtmlPath, { hash })
  }

  logWindow.once('ready-to-show', () => {
    logWindow?.show()
  })

  logWindow.on('closed', () => {
    logger.info('日志窗口已关闭')
    logWindow = null
  })
}

// ==================== 虚拟显示器询问弹窗 ====================
// 真实显示器回来了但有任务在跑，后端不拆虚拟屏、改为问用户。此时虚拟屏是主显示器，
// 主窗口和任务栏都留在看不见的那块上，所以这个弹窗必须另开窗口、放到回来的那块屏
// 右下角，而不是画在主窗口里。它只是一个壳：数据由主窗口渲染进程从后端消息转来，
// 拆不拆由弹窗自己调后端接口。

interface VirtualDisplayPromptPayload {
  /** 回来的真实显示设备名 */
  returned: string[]
  /** 回来那块屏的工作区，物理像素；后端读不到时为空 */
  monitor?: { left: number; top: number; right: number; bottom: number } | null
}

let virtualDisplayPromptPayload: VirtualDisplayPromptPayload | null = null

const VDD_PROMPT_WIDTH = 460
const VDD_PROMPT_HEIGHT = 240
const VDD_PROMPT_MARGIN = 16

function isVirtualDisplayPromptPayload(value: unknown): value is VirtualDisplayPromptPayload {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<VirtualDisplayPromptPayload>
  if (!Array.isArray(candidate.returned)) return false
  const monitor = candidate.monitor
  if (monitor == null) return true
  return (
    typeof monitor === 'object' &&
    ['left', 'top', 'right', 'bottom'].every(
      key => typeof (monitor as Record<string, unknown>)[key] === 'number'
    )
  )
}

/**
 * 弹窗该落在哪块屏。
 * 后端给的矩形是物理像素，Electron 的屏幕坐标是 DIP，Windows 上要先换算再找屏；
 * 没给矩形就挑一块非主显示器——虚拟屏是在无输出时挂上的，此刻一定是主显示器。
 */
function resolveVirtualDisplayPromptDisplay(payload: VirtualDisplayPromptPayload): Display {
  const rect = payload.monitor
  if (rect) {
    const physicalCenter = {
      x: Math.round((rect.left + rect.right) / 2),
      y: Math.round((rect.top + rect.bottom) / 2),
    }
    const dipCenter =
      process.platform === 'win32' && typeof screen.screenToDipPoint === 'function'
        ? screen.screenToDipPoint(physicalCenter)
        : physicalCenter
    return screen.getDisplayNearestPoint(dipCenter)
  }
  const primary = screen.getPrimaryDisplay()
  return screen.getAllDisplays().find(display => display.id !== primary.id) ?? primary
}

function virtualDisplayPromptBounds(display: Display): Rectangle {
  const area = display.workArea
  return {
    x: area.x + area.width - VDD_PROMPT_WIDTH - VDD_PROMPT_MARGIN,
    y: area.y + area.height - VDD_PROMPT_HEIGHT - VDD_PROMPT_MARGIN,
    width: VDD_PROMPT_WIDTH,
    height: VDD_PROMPT_HEIGHT,
  }
}

function showVirtualDisplayPrompt(payload: VirtualDisplayPromptPayload): void {
  virtualDisplayPromptPayload = payload
  const display = resolveVirtualDisplayPromptDisplay(payload)
  const bounds = virtualDisplayPromptBounds(display)

  if (virtualDisplayPromptWindow && !virtualDisplayPromptWindow.isDestroyed()) {
    virtualDisplayPromptWindow.setBounds(bounds)
    virtualDisplayPromptWindow.webContents.send('vdd-prompt:data', payload)
    virtualDisplayPromptWindow.showInactive()
    return
  }

  logger.info(
    `创建虚拟显示器询问弹窗：回来的显示器 ${payload.returned.join(', ')}，落在显示器 ${display.id} 的 ${JSON.stringify(bounds)}`
  )

  const win = new BrowserWindow({
    ...bounds,
    frame: false,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    show: false,
    title: '虚拟显示器 - AUTO-MAS',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    autoHideMenuBar: true,
  })
  virtualDisplayPromptWindow = win
  win.setMenuBarVisibility(false)

  const hash = '/vdd-prompt'
  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    win.loadURL(`${devServer}#${hash}`)
  } else {
    win.loadFile(path.join(app.getAppPath(), 'dist', 'index.html'), { hash })
  }

  win.once('ready-to-show', () => {
    if (win.isDestroyed()) return
    // 创建时给的 bounds 可能被 DPI 折算挪动，显示前再摆一次
    win.setBounds(bounds)
    // 不抢焦点：正在跑的脚本可能靠键盘操作游戏，焦点一走就打断
    win.showInactive()
  })

  win.on('closed', () => {
    if (virtualDisplayPromptWindow === win) {
      virtualDisplayPromptWindow = null
      virtualDisplayPromptPayload = null
    }
    logger.info('虚拟显示器询问弹窗已关闭')
  })
}

function closeVirtualDisplayPrompt(): void {
  const win = virtualDisplayPromptWindow
  virtualDisplayPromptWindow = null
  virtualDisplayPromptPayload = null
  if (win && !win.isDestroyed()) {
    win.close()
  }
}

ipcMain.handle('vdd-prompt:show', (_event, payload: unknown) => {
  if (!isVirtualDisplayPromptPayload(payload)) {
    logger.warn(`虚拟显示器询问弹窗收到无法识别的数据: ${JSON.stringify(payload)}`)
    return { success: false, error: 'invalid payload' }
  }
  try {
    showVirtualDisplayPrompt(payload)
    return { success: true }
  } catch (error) {
    logger.error('打开虚拟显示器询问弹窗失败:', error)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
})

ipcMain.handle('vdd-prompt:close', () => {
  closeVirtualDisplayPrompt()
})

// 弹窗页面挂载后自己来取：主进程在 did-finish-load 时推送会早于 Vue 组件注册监听
ipcMain.handle('vdd-prompt:get', () => virtualDisplayPromptPayload)

// 日志系统 IPC 处理器
ipcMain.handle(
  'log:write',
  async (_event, level: string, moduleName: string, ...args: unknown[]) => {
    try {
      const rendererLogger = getLogger(moduleName)
      const message = args
        .map(arg => (typeof arg === 'object' ? JSON.stringify(arg) : String(arg)))
        .join(' ')

      switch (level) {
        case 'debug':
          rendererLogger.debug(message)
          break
        case 'info':
          rendererLogger.info(message)
          break
        case 'warn':
          rendererLogger.warn(message)
          break
        case 'error':
          rendererLogger.error(message)
          break
        default:
          rendererLogger.info(message)
      }
    } catch (error) {
      console.error('写入日志失败:', error)
    }
  }
)

ipcMain.handle('log:export', async () => {
  try {
    if (!mainWindow) return { success: false, error: '窗口未初始化' }

    const appRoot = getAppRoot()
    const debugDir = path.join(appRoot, 'debug')

    if (!fs.existsSync(debugDir)) {
      return { success: false, error: '日志目录不存在' }
    }

    // 选择保存位置
    const result = await dialog.showSaveDialog(mainWindow, {
      title: '导出日志',
      defaultPath: `logs-${new Date().toISOString().slice(0, 10)}.zip`,
      filters: [{ name: 'ZIP文件', extensions: ['zip'] }],
    })

    if (result.canceled || !result.filePath) {
      return { success: false, error: '用户取消' }
    }

    const zipPath = result.filePath

    // 创建 ZIP 文件
    const zip = new AdmZip()

    // 读取 debug 目录下的所有文件
    const files = fs.readdirSync(debugDir)

    if (files.length === 0) {
      return { success: false, error: '日志目录为空，没有可导出的文件' }
    }

    // 将所有日志文件添加到 ZIP
    for (const file of files) {
      const filePath = path.join(debugDir, file)
      const stat = fs.statSync(filePath)

      if (stat.isFile()) {
        zip.addLocalFile(filePath)
        logger.info(`添加文件到压缩包: ${file}`)
      } else if (stat.isDirectory() && file === 'maaend-login') {
        zip.addLocalFolder(filePath, 'maaend-login')
        logger.info('添加 MaaEnd 登录错误截图到压缩包')
      }
    }

    // 保存 ZIP 文件
    zip.writeZip(zipPath)
    logger.info(`日志压缩包已导出: ${zipPath}`)

    return {
      success: true,
      message: '日志压缩包导出成功',
      zipPath: zipPath,
    }
  } catch (error) {
    logger.error('导出日志失败:', error)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
})

interface IssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

// scriptId 只有按脚本导出的问题包（MFW）才用，其余导出函数不接这个参数
function registerIssueReportExporter(
  ipcChannel: string,
  title: string,
  fileNamePrefix: string | ((appRoot: string, scriptId: string) => string),
  create: (
    appRoot: string,
    zipPath: string,
    scriptId: string
  ) => IssueReportResult | Promise<IssueReportResult>
): void {
  ipcMain.handle(ipcChannel, async (_event, rawScriptId?: unknown) => {
    try {
      if (!mainWindow) return { success: false, error: '窗口未初始化' }

      const scriptId = typeof rawScriptId === 'string' ? rawScriptId : ''
      const appRoot = getAppRoot()
      const prefix =
        typeof fileNamePrefix === 'function' ? fileNamePrefix(appRoot, scriptId) : fileNamePrefix
      const result = await dialog.showSaveDialog(mainWindow, {
        title,
        defaultPath: `${prefix}-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.zip`,
        filters: [{ name: 'ZIP文件', extensions: ['zip'] }],
      })

      if (result.canceled || !result.filePath) {
        return { success: false, error: '用户取消' }
      }

      return await create(appRoot, result.filePath, scriptId)
    } catch (error) {
      logger.error(`${title}失败:`, error)
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
      }
    }
  })
}

registerIssueReportExporter(
  'maaend:exportIssueReport',
  '导出 MaaEnd 问题包',
  'MaaEnd-logs',
  createMaaEndIssueReport
)
registerIssueReportExporter(
  'okww:exportIssueReport',
  '导出 OK-WW 问题包',
  'OK-WW-logs',
  createOkwwIssueReport
)
registerIssueReportExporter(
  'oknte:exportIssueReport',
  '导出 OK-NTE 问题包',
  'OK-NTE-logs',
  createOkNteIssueReport
)
registerIssueReportExporter(
  'zzzod:exportIssueReport',
  '导出 ZZZ-OD 问题包',
  'ZZZ-OD-logs',
  createZzzOdIssueReport
)
registerIssueReportExporter(
  'maafw:exportIssueReport',
  '导出 MFW 问题包',
  maafwIssueReportFileNamePrefix,
  createMaaFWIssueReport
)
registerIssueReportExporter(
  'm9a:exportIssueReport',
  '导出 M9A 问题包',
  'M9A-logs',
  createM9AIssueReport
)

ipcMain.handle('maafw:listIssueReportScripts', (_event, configTypes?: unknown) => {
  const types = Array.isArray(configTypes)
    ? configTypes.filter((type): type is string => typeof type === 'string')
    : []
  return listMaaFWIssueReportScripts(getAppRoot(), types)
})

ipcMain.handle('data:backup', async () => {
  let partialPath: string | undefined

  try {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return { success: false, error: '窗口未初始化' }
    }

    const result = await dialog.showSaveDialog(mainWindow, {
      title: '导出数据备份',
      defaultPath: `AUTO-MAS-backup-${new Date().toISOString().slice(0, 10)}.zip`,
      filters: [{ name: 'ZIP文件', extensions: ['zip'] }],
    })

    if (result.canceled || !result.filePath) {
      return { success: false, error: '用户取消' }
    }

    const zipPath = result.filePath
    partialPath = `${zipPath}.part-${process.pid}-${Date.now()}`
    const response = await fetch(`${getLocalApiEndpoint()}/api/setting/backup`, {
      method: 'GET',
    })

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ''}`
      )
    }
    if (!response.body) {
      throw new Error('后端未返回备份文件内容')
    }

    const file = await fs.promises.open(partialPath, 'wx')
    try {
      for await (const chunk of response.body as unknown as AsyncIterable<Uint8Array>) {
        await file.write(chunk)
      }
    } finally {
      await file.close()
    }

    await fs.promises.rename(partialPath, zipPath)
    partialPath = undefined
    logger.info(`数据备份已导出: ${zipPath}`)

    return {
      success: true,
      message: '数据备份导出成功',
      zipPath,
    }
  } catch (error) {
    if (partialPath) {
      await fs.promises.unlink(partialPath).catch(() => undefined)
    }

    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出数据备份失败: ${errorMsg}`)
    return { success: false, error: errorMsg }
  }
})

// 传了 fromOffset 走增量形态，返回 { content, size, reset }；否则沿用整份字符串
ipcMain.handle(
  'log:getContent',
  async (_event, lines?: number, fileName?: string, fromOffset?: number) => {
    const logPath = path.join(getAppRoot(), 'debug', fileName || 'frontend.log')
    try {
      if (typeof fromOffset === 'number') {
        return await readLogIncrement(logPath, fromOffset)
      }
      return await readLogContent(logPath, lines)
    } catch (error) {
      logger.error('读取日志内容失败:', error)
      // 增量形态下按「没有新内容」处理，下一轮继续从同一偏移读
      return typeof fromOffset === 'number' ? { content: '', size: fromOffset, reset: false } : ''
    }
  }
)

ipcMain.handle('log:openWindow', async (_event, file?: LogWindowFile) => {
  try {
    createLogWindow(file)
    return { success: true }
  } catch (error) {
    logger.error('打开日志窗口失败:', error)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
})

// IPC处理函数
ipcMain.handle('open-dev-tools', () => {
  if (mainWindow) {
    mainWindow.webContents.openDevTools({ mode: 'undocked' })
  }
})

// 窗口控制
ipcMain.handle('window-minimize', () => {
  if (mainWindow) {
    mainWindow.minimize()
  }
})

ipcMain.handle('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize()
    } else {
      mainWindow.maximize()
    }
  }
})

ipcMain.handle('window-close', () => {
  requestRendererClose('renderer 请求关闭窗口')
})

ipcMain.handle('get-window-activity', () => {
  if (lastWindowActivity) {
    return lastWindowActivity
  }

  if (!mainWindow || mainWindow.isDestroyed()) {
    return 'background' as const
  }

  return mainWindow.isVisible() && !mainWindow.isMinimized() ? 'visible' : 'background'
})

// 窗口聚焦（从托盘/最小化状态恢复并激活到前台）
ipcMain.handle('window-focus', () => {
  if (mainWindow) {
    // 如果窗口最小化，先恢复
    if (mainWindow.isMinimized()) {
      mainWindow.restore()
    }
    // 恢复任务栏图标
    mainWindow.setSkipTaskbar(false)
    // 显示窗口
    mainWindow.show()
    // 聚焦窗口
    mainWindow.focus()
  }
})

// 添加应用重启处理器
ipcMain.handle('app-restart', () => {
  logger.info('重启应用程序...')
  relaunchAfterQuit = true
  requestRendererClose('应用重启')
})

// renderer 仅在后端优雅关闭或超时兜底完成后调用，作为最终退出确认。
ipcMain.handle('app-quit', () => {
  finishCoordinatedQuit()
})

// 添加进程管理相关的 IPC 处理器
ipcMain.handle('get-related-processes', async () => {
  try {
    const { getRelatedProcesses } = await import('./utils/processManager')
    return await getRelatedProcesses()
  } catch {
    logger.error('获取进程信息失败')
    return []
  }
})

ipcMain.handle('kill-all-processes', async () => {
  try {
    await forceKillRelatedProcesses()
    return { success: true }
  } catch (error) {
    logger.error('强制清理进程失败')
    return { success: false, error: error instanceof Error ? error.message : String(error) }
  }
})

ipcMain.handle('window-is-maximized', () => {
  return mainWindow ? mainWindow.isMaximized() : false
})

ipcMain.handle('select-folder', async () => {
  if (!mainWindow) return null
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: '选择文件夹',
  })
  return result.canceled ? null : result.filePaths[0]
})

ipcMain.handle('select-file', async (event, filters = []) => {
  if (!mainWindow) return []
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    title: '选择文件',
    filters: filters.length > 0 ? filters : [{ name: '所有文件', extensions: ['*'] }],
  })
  return result.canceled ? [] : result.filePaths
})

// 在系统默认浏览器中打开URL
ipcMain.handle('open-url', async (_event, url: string) => {
  try {
    await shell.openExternal(url)
    return { success: true }
  } catch (error) {
    if (error instanceof Error) {
      logger.error(`打开链接失败: ${error.message}`)
      return { success: false, error: error.message }
    } else {
      logger.error(`未知错误: ${error}`)
      return { success: false, error: String(error) }
    }
  }
})

// 打开文件
// shell.openPath 失败时不 reject，而是 resolve 一条非空的错误信息（没有关联程序、
// 文件不存在都走这条），丢掉返回值的话调用方永远收不到失败。
ipcMain.handle('open-file', async (_event, filePath: string) => {
  try {
    const failure = await shell.openPath(filePath)
    if (failure) {
      logger.error(`打开文件失败: ${failure}`)
      return { success: false, error: failure }
    }
    return { success: true }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logger.error(`打开文件失败: ${message}`)
    return { success: false, error: message }
  }
})

// 显示文件所在目录并选中文件
ipcMain.handle('show-item-in-folder', async (_event, filePath: string) => {
  try {
    shell.showItemInFolder(filePath)
  } catch (error) {
    logger.error(`显示文件所在目录失败: ${error}`)
    throw error
  }
})

// Runtime 上下文 - 初始化界面开局问一次：走没走 Runtime、回退日志文件、可用镜像键
ipcMain.handle('get-runtime-init-context', async () => resolveRuntimeInitContext())

// 关键文件检查 - 每次都重新检查exe文件是否存在
ipcMain.handle('check-critical-files', async () => {
  try {
    // Runtime 链路不再有 environment/python 这套目录，改问 Runtime doctor 要受管布局。
    const runtimeCheck = await checkCriticalFilesViaRuntime()
    if (runtimeCheck) return runtimeCheck

    const appRoot = getAppRoot()

    // 检查Python可执行文件
    const pythonPath = path.join(appRoot, 'environment', 'python', 'python.exe')
    const pythonExists = fs.existsSync(pythonPath)

    // 检查pip（通常与Python一起安装）
    const pipPath = path.join(appRoot, 'environment', 'python', 'Scripts', 'pip.exe')
    const pipExists = fs.existsSync(pipPath)

    // 检查Git可执行文件
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')
    const gitExists = fs.existsSync(gitPath)

    // 检查后端主文件
    const mainPyPath = path.join(appRoot, 'main.py')
    const mainPyExists = fs.existsSync(mainPyPath)

    const result = {
      pythonExists,
      pipExists,
      gitExists,
      mainPyExists,
    }

    logger.info('关键文件检查结果')
    return result
  } catch {
    logger.error('检查关键文件失败')
    return {
      pythonExists: false,
      pipExists: false,
      gitExists: false,
      mainPyExists: false,
    }
  }
})

// Python相关 - 已迁移到初始化服务
// 这些 IPC 处理器已在 initializationHandlers.ts 中实现

// 获取应用路径
ipcMain.handle('get-app-path', async (_event, name: Parameters<typeof app.getPath>[0]) => {
  try {
    return app.getPath(name)
  } catch {
    logger.error(`获取路径 ${name} 失败`)
    return ''
  }
})

// Git相关 - 已迁移到初始化服务
// 这些 IPC 处理器已在 initializationHandlers.ts 中实现

// Git 更新检查和仓库管理 - 已迁移到初始化服务
// 这些 IPC 处理器已在 initializationHandlers.ts 中实现

// 配置文件操作
ipcMain.handle('save-config', async (_event, config) => {
  try {
    const appRoot = getAppRoot()
    const configDir = path.join(appRoot, 'config')
    const configPath = path.join(configDir, 'frontend_config.json')

    // 确保config目录存在
    if (!fs.existsSync(configDir)) {
      fs.mkdirSync(configDir, { recursive: true })
    }

    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8')
    logger.info(`配置已保存到: ${configPath}`)

    // 如果是UI配置更新，需要更新托盘状态
    if (config.UI) {
      updateTrayVisibility(config)
      if (Array.isArray(config.UI.TrayItems) && config.UI.TrayItems.length) {
        rebuildTrayMenu(config.UI.TrayItems)
      }
    }
  } catch (error) {
    logger.error('保存配置文件失败')
    throw error
  }
})

// 新增：实时更新托盘状态的IPC处理器
ipcMain.handle('update-tray-settings', async (_event, uiSettings) => {
  try {
    // 先更新配置文件
    const currentConfig = loadConfig()
    currentConfig.UI = { ...currentConfig.UI, ...uiSettings }
    saveConfig(currentConfig)

    // 立即更新托盘状态
    updateTrayVisibility(currentConfig)

    logger.info('托盘设置已更新')
    return true
  } catch (error) {
    logger.error('更新托盘设置失败')
    throw error
  }
})

// 更新托盘自定义菜单项
ipcMain.handle('update-tray-config', async (_event, trayItems: TrayItem[]) => {
  try {
    const currentConfig = loadConfig()
    currentConfig.UI = { ...currentConfig.UI, TrayItems: trayItems }
    saveConfig(currentConfig)

    // 销毁并重建托盘，强制右键菜单即时刷新为新配置；刷新失败不应导致配置保存失败
    try {
      if (tray) destroyTray()
      updateTrayVisibility(currentConfig)
    } catch (refreshError) {
      logger.error('刷新托盘菜单失败', refreshError)
    }

    logger.info('托盘菜单项已更新')
    return true
  } catch (error) {
    logger.error('更新托盘菜单项失败')
    throw error
  }
})

// 新增：同步后端配置的IPC处理器
ipcMain.handle('sync-backend-config', async (_event, backendSettings) => {
  try {
    const currentConfig = loadConfig()

    // 同步UI配置
    if (backendSettings.UI) {
      currentConfig.UI = { ...currentConfig.UI, ...backendSettings.UI }
    }

    // 同步Start配置
    if (backendSettings.Start) {
      currentConfig.Start = { ...currentConfig.Start, ...backendSettings.Start }
    }

    // 同步Update配置
    if (backendSettings.Update) {
      currentConfig.Update = { ...currentConfig.Update, ...backendSettings.Update }
    }

    // 同步遥测开关，供渲染进程在 Sentry 初始化前读取
    if (backendSettings.Function) {
      currentConfig.Function = { ...currentConfig.Function, ...backendSettings.Function }
    }

    // 保存到前端配置文件
    saveConfig(currentConfig)
    setMainTelemetryEnabled(currentConfig.Function?.IfEnableTelemetry !== false)

    // 更新托盘状态
    updateTrayVisibility(currentConfig)

    logger.info('后端配置已同步')
    return true
  } catch (error) {
    logger.error('同步后端配置失败')
    throw error
  }
})

ipcMain.handle('load-config', async () => {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (fs.existsSync(configPath)) {
      const config = fs.readFileSync(configPath, 'utf8')
      logger.info(`从文件加载配置: ${configPath}`)
      return JSON.parse(config)
    }

    return null
  } catch {
    logger.error('加载配置文件失败')
    return null
  }
})

ipcMain.handle('reset-config', async () => {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (fs.existsSync(configPath)) {
      fs.unlinkSync(configPath)
      logger.info(`配置文件已删除: ${configPath}`)
    }
  } catch (error) {
    logger.error('重置配置文件失败')
    throw error
  }
})

// 应用初始化版本管理（保存前端版本号，版本号不一致时需要重新初始化）
ipcMain.handle('get-initialized-version', async () => {
  try {
    const config = loadConfig()
    return config.initializedVersion ?? null
  } catch (error) {
    logger.error('读取初始化版本失败', error)
    return null
  }
})

ipcMain.handle('set-initialized-version', async (_event, version: string) => {
  try {
    const config = loadConfig()
    config.initializedVersion = version
    saveConfig(config)
    logger.info(`初始化版本已保存: ${version}`)
    return true
  } catch (error) {
    logger.error('保存初始化版本失败', error)
    return false
  }
})

// Runtime 灰度开关：持久化设置 + 当前生效值（供设置界面展示来源与效果，重启后生效）
ipcMain.handle('get-runtime-launch-mode', async () => {
  try {
    const config = loadConfig()
    const persisted = isPersistedRuntimeLaunchMode(config.Runtime?.LaunchMode)
      ? config.Runtime.LaunchMode
      : 'auto'
    const resolution = resolveRuntimeLaunchModeDetail(getAppRoot())
    return { persisted, mode: resolution.mode, source: resolution.source }
  } catch (error) {
    logger.error('读取 Runtime 启动方式失败', error)
    return { persisted: 'auto', mode: 'off', source: 'default' }
  }
})

ipcMain.handle('set-runtime-launch-mode', async (_event, mode: unknown) => {
  if (!isPersistedRuntimeLaunchMode(mode)) {
    throw new TypeError(`不支持的 Runtime 启动方式: ${String(mode)}`)
  }

  try {
    const config = loadConfig()
    config.Runtime = { ...config.Runtime, LaunchMode: mode }
    saveConfig(config)
    logger.info(`Runtime 启动方式已设置为: ${mode}`)

    const resolution = resolveRuntimeLaunchModeDetail(getAppRoot())
    return { persisted: mode, mode: resolution.mode, source: resolution.source }
  } catch (error) {
    logger.error('保存 Runtime 启动方式失败', error)
    throw error
  }
})

// 应用生命周期
// 保证应用单例运行
const gotTheLock = app.requestSingleInstanceLock()

if (!gotTheLock) {
  app.quit()
  process.exit(0)
}

// 在沙箱环境下运行会导致无法启动子进程，强制禁用沙箱
app.commandLine.appendSwitch('no-sandbox')

app.on('second-instance', () => {
  if (mainWindow) {
    // 如果窗口最小化，先恢复
    if (mainWindow.isMinimized()) {
      mainWindow.restore()
    }
    mainWindow.setSkipTaskbar(false)
    mainWindow.show()
    mainWindow.focus()
  }
})

// GPU 进程崩溃同样会让窗口变黑，此前同样不会在日志里留下任何痕迹。
app.on('child-process-gone', (_event, details) => {
  if (details.reason === 'clean-exit') return
  logger.error(
    `子进程异常退出: type=${details.type}, reason=${details.reason}, exitCode=${details.exitCode}`
  )
})

app.on('will-quit', () => {
  globalShortcut.unregisterAll()
})

app.on('before-quit', event => {
  if (canElectronExitImmediately({ coordinatedQuit, forceQuitInProgress, quitRequestInFlight })) {
    return
  }
  event.preventDefault()
  if (forceQuitInProgress) {
    logger.warn('强制清理仍在进行，暂不允许 Electron 提前退出')
    return
  }
  requestRendererClose('Electron before-quit')
})

app.whenReady().then(async () => {
  logger.info(`应用版本: ${app.getVersion()}`)
  logger.info(`Electron版本: ${process.versions.electron}`)
  logger.info(`Node版本: ${process.versions.node}`)
  logger.info(`平台: ${process.platform}`)

  // 注册文件操作处理器（在窗口创建之前注册）
  registerFileHandlers()
  logger.info('文件操作处理器已注册')

  // 注册 OK-WW 与鸣潮安装路径发现处理器
  registerOkwwPathDiscoveryHandlers()
  logger.info('OK-WW 路径发现处理器已注册')

  registerStopAllTasksShortcut()

  // 检查管理员权限
  if (!isRunningAsAdmin()) {
    logger.warn('应用未以管理员权限运行')
    // 在生产环境中，可以选择是否强制要求管理员权限
    // 这里先创建窗口，让用户选择是否重新启动
  } else {
    logger.info('应用以管理员权限运行')
  }

  powerMonitor.on('resume', () => {
    logger.info('主进程检测到系统恢复，通知 renderer 检查后端连接')
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('system-resumed')
    }
  })

  createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (canElectronExitImmediately({ coordinatedQuit, forceQuitInProgress, quitRequestInFlight })) {
      app.quit()
    } else if (!forceQuitInProgress && !quitRequestInFlight) {
      void forceQuitAfterRendererTimeout('所有 renderer 窗口意外关闭')
    }
  }
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})
