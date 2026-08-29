import { spawn } from 'child_process'
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
import { checkEnvironment, getAppRoot } from './services/environmentService'
import {
  registerInitializationHandlers,
  getBackendService,
  getLocalApiEndpoint,
} from './ipc/initializationHandlers'
import { registerFileHandlers } from './ipc/fileHandlers'
import { registerOkwwPathDiscoveryHandlers } from './ipc/okwwPathDiscoveryHandlers'
import {
  canElectronExitImmediately,
  canRequestRendererClose,
  markForceQuitFailed,
} from './quitCoordinationState'

import { getLogger, initializeLogger } from './services/logger'
import { createMaaEndIssueReport } from './services/maaEndIssueReportService'
import AdmZip = require('adm-zip')

// 初始化日志系统（必须在创建 logger 之前）
initializeLogger()

const logger = getLogger('主进程')
const STOP_ALL_TASKS_SHORTCUT = 'Control+Shift+Alt+M'
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
    const result = await getBackendService().forceStopBackend()
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

// 重新以管理员权限启动应用
function restartAsAdmin(): void {
  if (process.platform === 'win32') {
    const exePath = process.execPath
    const args = process.argv.slice(1)

    // 使用PowerShell以管理员权限启动
    spawn(
      'powershell',
      [
        '-Command',
        `Start-Process -FilePath "${exePath}" -ArgumentList "${args.join(' ')}" -Verb RunAs`,
      ],
      {
        detached: true,
        stdio: 'ignore',
      }
    )

    app.quit()
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

  [key: string]: any
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
    })
    forceQuitInProgress = retryableState.forceQuitInProgress
    quitRequestInFlight = retryableState.quitRequestInFlight
    dialog.showErrorBox(
      'AUTO-MAS 无法安全退出',
      `未能确认后端进程已退出，前端将保持运行以避免遗留后台进程。\n\n${errorMsg}`
    )
    if ((!mainWindow || mainWindow.isDestroyed()) && app.isReady()) {
      try {
        createWindow()
      } catch (windowError) {
        const windowErrorMsg =
          windowError instanceof Error ? windowError.message : String(windowError)
        logger.error(`强制清理失败后重建窗口失败: ${windowErrorMsg}`)
      }
    }
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
function createLogWindow() {
  // 如果日志窗口已存在，则聚焦并返回
  if (logWindow && !logWindow.isDestroyed()) {
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

  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    logWindow.loadURL(`${devServer}#/logs`)
  } else {
    const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
    logWindow.loadFile(indexHtmlPath, { hash: '/logs' })
  }

  logWindow.once('ready-to-show', () => {
    logWindow?.show()
  })

  logWindow.on('closed', () => {
    logger.info('日志窗口已关闭')
    logWindow = null
  })
}

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

ipcMain.handle('maaend:exportIssueReport', async () => {
  try {
    if (!mainWindow) return { success: false, error: '窗口未初始化' }

    const result = await dialog.showSaveDialog(mainWindow, {
      title: '导出 MaaEnd 问题包',
      defaultPath: `MaaEnd-logs-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.zip`,
      filters: [{ name: 'ZIP文件', extensions: ['zip'] }],
    })

    if (result.canceled || !result.filePath) {
      return { success: false, error: '用户取消' }
    }

    return createMaaEndIssueReport(getAppRoot(), result.filePath)
  } catch (error) {
    logger.error('导出 MaaEnd 问题包失败:', error)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
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

ipcMain.handle('log:getContent', async (_event, lines?: number, fileName?: string) => {
  try {
    const appRoot = getAppRoot()
    const logFile = fileName || 'frontend.log'
    const logPath = path.join(appRoot, 'debug', logFile)

    if (!fs.existsSync(logPath)) {
      return ''
    }

    const content = fs.readFileSync(logPath, 'utf-8')

    if (!lines || lines === 0) {
      return content
    }

    // 返回最后 N 行
    const allLines = content.split('\n')
    return allLines.slice(-lines).join('\n')
  } catch (error) {
    logger.error('读取日志内容失败:', error)
    return ''
  }
})

ipcMain.handle('log:openWindow', async () => {
  try {
    createLogWindow()
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
ipcMain.handle('open-file', async (_event, filePath: string) => {
  try {
    await shell.openPath(filePath)
  } catch (error) {
    logger.error(`打开文件失败: ${error}`)
    throw error
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

// 环境检查
ipcMain.handle('check-environment', async () => {
  const appRoot = getAppRoot()
  return checkEnvironment(appRoot)
})

// 关键文件检查 - 每次都重新检查exe文件是否存在
ipcMain.handle('check-critical-files', async () => {
  try {
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

// 获取当前主题信息
ipcMain.handle('get-theme-info', async () => {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    let themeMode = 'system'
    let themeColor = 'blue'

    // 尝试从配置文件读取主题设置
    if (fs.existsSync(configPath)) {
      try {
        const configData = fs.readFileSync(configPath, 'utf8')
        const config = JSON.parse(configData)
        themeMode = config.themeMode || 'system'
        themeColor = config.themeColor || 'blue'
      } catch {
        logger.warn('读取主题配置失败，使用默认值')
      }
    }

    // 检测系统主题
    const systemTheme = nativeTheme.shouldUseDarkColors ? 'dark' : 'light'

    // 确定实际使用的主题
    let actualTheme = themeMode
    if (themeMode === 'system') {
      actualTheme = systemTheme
    }

    const themeColors: Record<string, string> = {
      blue: '#1677ff',
      purple: '#722ed1',
      cyan: '#13c2c2',
      green: '#52c41a',
      magenta: '#eb2f96',
      pink: '#eb2f96',
      red: '#ff4d4f',
      orange: '#fa8c16',
      yellow: '#fadb14',
      volcano: '#fa541c',
      geekblue: '#2f54eb',
      lime: '#a0d911',
      gold: '#faad14',
    }

    return {
      themeMode,
      themeColor,
      actualTheme,
      systemTheme,
      isDark: actualTheme === 'dark',
      primaryColor: themeColors[themeColor] || themeColors.blue,
    }
  } catch {
    logger.error('获取主题信息失败')
    return {
      themeMode: 'system',
      themeColor: 'blue',
      actualTheme: 'light',
      systemTheme: 'light',
      isDark: false,
      primaryColor: '#1677ff',
    }
  }
})

// 获取应用路径
ipcMain.handle('get-app-path', async (_event, name: any) => {
  try {
    return app.getPath(name)
  } catch {
    logger.error(`获取路径 ${name} 失败`)
    return ''
  }
})

// 获取对话框专用的主题信息
ipcMain.handle('get-theme', async () => {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    let themeMode = 'system'

    // 尝试从配置文件读取主题设置
    if (fs.existsSync(configPath)) {
      try {
        const configData = fs.readFileSync(configPath, 'utf8')
        const config = JSON.parse(configData)
        themeMode = config.themeMode || 'system'
      } catch {
        logger.warn('读取主题配置失败，使用默认值')
      }
    }

    // 检测系统主题
    const systemTheme = nativeTheme.shouldUseDarkColors ? 'dark' : 'light'

    // 确定实际使用的主题
    let actualTheme = themeMode
    if (themeMode === 'system') {
      actualTheme = systemTheme
    }

    return actualTheme
  } catch {
    logger.error('获取对话框主题失败')
    return nativeTheme.shouldUseDarkColors ? 'dark' : 'light'
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

// 管理员权限相关
ipcMain.handle('check-admin', () => {
  return isRunningAsAdmin()
})

ipcMain.handle('restart-as-admin', () => {
  restartAsAdmin()
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
    } else if (!forceQuitInProgress) {
      void forceQuitAfterRendererTimeout('所有 renderer 窗口意外关闭')
    }
  }
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})
