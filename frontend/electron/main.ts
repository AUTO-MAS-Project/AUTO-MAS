import { spawn } from 'child_process'
import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeImage,
  nativeTheme,
  screen,
  shell,
  Tray,
  type Display,
  type Rectangle,
} from 'electron'
import { randomUUID } from 'crypto'
import * as fs from 'fs'
import * as path from 'path'
import { checkEnvironment, getAppRoot } from './services/environmentService'
import { getRendererDevServerUrl } from './services/rendererRuntimePolicy'
import {
  registerInitializationHandlers,
  cleanupInitializationResources,
  getManagedBackendProcesses,
  prewarmBackend,
} from './ipc/initializationHandlers'
import { registerFileHandlers } from './ipc/fileHandlers'

import { getLogger, initializeLogger } from './services/logger'
import { buildElevationLaunchSpec } from './services/elevationService'
import { isProcessElevated } from './services/adminPolicy'
import {
  isTrustedRendererNavigation,
  normalizeExternalNavigation,
  type RendererNavigationPolicy,
} from './services/rendererSecurityPolicy'
import {
  isSafeDocumentPath,
  resolveDirectChildPath,
  resolveRendererFilePath,
} from './services/fileAccessPolicy'
import {
  buildElevationHandoffArguments,
  completeElevationHandoff,
  readElevationHandoffToken,
  waitForSingleInstanceLock,
} from './services/singleInstanceHandoff'
import AdmZip = require('adm-zip')

// 初始化日志系统（必须在创建 logger 之前）
initializeLogger()

const logger = getLogger('主进程')

const ELEVATION_HANDOFF_TIMEOUT_MS = 60_000
let pendingElevationHandoffToken: string | null = null
let pendingElevationHandoffTimeout: NodeJS.Timeout | null = null

function clearPendingElevationHandoff(): void {
  pendingElevationHandoffToken = null
  if (pendingElevationHandoffTimeout) {
    clearTimeout(pendingElevationHandoffTimeout)
    pendingElevationHandoffTimeout = null
  }
}

// 旧实例只在带随机令牌的新实例到达后释放单例锁；UAC 取消时继续运行。
async function restartAsAdmin(): Promise<{ success: boolean; error?: string }> {
  if (process.platform !== 'win32') {
    return { success: false, error: 'Administrator restart is only supported on Windows' }
  }
  if (pendingElevationHandoffToken) {
    return { success: false, error: 'Administrator restart is already pending' }
  }

  const handoffToken = randomUUID()
  pendingElevationHandoffToken = handoffToken
  pendingElevationHandoffTimeout = setTimeout(() => {
    logger.warn('管理员重启交接超时，当前实例继续运行')
    clearPendingElevationHandoff()
  }, ELEVATION_HANDOFF_TIMEOUT_MS)

  const forwardedArguments = buildElevationHandoffArguments(process.argv.slice(1), handoffToken)
  const launchSpec = buildElevationLaunchSpec(process.execPath, forwardedArguments)

  return await new Promise(resolve => {
    const helper = spawn(launchSpec.command, launchSpec.args, launchSpec.options)
    let settled = false
    const finish = (result: { success: boolean; error?: string }) => {
      if (settled) return
      settled = true
      if (!result.success) {
        clearPendingElevationHandoff()
      }
      resolve(result)
    }

    helper.once('error', error => {
      finish({ success: false, error: `Unable to request administrator restart: ${error.message}` })
    })
    helper.once('close', code => {
      if (code === 0) {
        finish({ success: true })
        return
      }
      finish({
        success: false,
        error:
          code == null ? 'Administrator restart was cancelled' : `Elevation helper exited ${code}`,
      })
    })
  })
}

let tray: Tray | null = null
let isQuitting = false
let shutdownCleanupStarted = false
let shutdownCleanupComplete = false
let shutdownCleanupPromise: Promise<void> | null = null
let saveWindowStateTimeout: NodeJS.Timeout | null = null
let isInitialStartup = true // 标记是否为初次启动
const isAutoStart = process.argv.includes('--auto-start') // 是否由开机自启动任务计划拉起

const HEARTBEAT_LOG_KEYWORD_RE = /(\bping\b|\bpong\b|heartbeat|心跳)/i

function runShutdownCleanup(): Promise<void> {
  if (shutdownCleanupPromise) {
    return shutdownCleanupPromise
  }
  shutdownCleanupStarted = true
  logger.info('应用准备退出，安全停止当前实例管理的后端')

  if (saveWindowStateTimeout) {
    clearTimeout(saveWindowStateTimeout)
    saveWindowStateTimeout = null
  }
  destroyTray()

  shutdownCleanupPromise = cleanupInitializationResources()
    .then(result => {
      if (result.success) {
        logger.info('当前实例管理的后端资源清理完成')
      } else {
        logger.warn(`当前实例管理的后端未停止: ${result.error}`)
      }
    })
    .catch(error => {
      logger.error(`安全清理后端资源失败: ${error instanceof Error ? error.message : error}`)
    })
  return shutdownCleanupPromise
}

function shouldDropHeartbeatProcessLog(
  level: string,
  moduleName: string,
  message: string
): boolean {
  const isProd = app.isPackaged
  if (!isProd) {
    return false
  }
  if (!['debug', 'info'].includes(level)) {
    return false
  }
  if (!HEARTBEAT_LOG_KEYWORD_RE.test(message)) {
    return false
  }

  // 仅过滤心跳过程日志，避免影响其他模块的普通业务日志。
  return moduleName.includes('WebSocket') || moduleName.includes('WS')
}

// 配置接口
interface AppConfig {
  UI: {
    IfShowTray: boolean
    IfToTray: boolean
    IfHideCloseButton: boolean
    location: string
    maximized: boolean
    size: string
  }
  Start: {
    IfMinimizeDirectly: boolean
    IfSelfStart: boolean
  }
  Update: {
    IfAutoUpdate: boolean
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
}

//加载配置
function loadConfig(): AppConfig {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (fs.existsSync(configPath)) {
      const configData = fs.readFileSync(configPath, 'utf8')
      const config = JSON.parse(configData)
      return { ...defaultConfig, ...config }
    }
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

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示窗口',
      click: () => {
        if (mainWindow) {
          if (mainWindow.isMinimized()) {
            mainWindow.restore()
          }
          mainWindow.setSkipTaskbar(false) // 恢复任务栏图标
          mainWindow.show()
          mainWindow.focus()
        }
      },
    },
    {
      label: '隐藏窗口',
      click: () => {
        if (mainWindow) {
          const currentConfig = loadConfig()
          if (currentConfig.UI.IfToTray) {
            mainWindow.setSkipTaskbar(true) // 隐藏任务栏图标
          }
          mainWindow.hide()
        }
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        isQuitting = true
        app.quit()
      },
    },
  ])

  tray.setContextMenu(contextMenu)
  tray.setToolTip('AUTO-MAS')

  // 双击托盘图标显示/隐藏窗口
  tray.on('double-click', () => {
    if (mainWindow) {
      const currentConfig = loadConfig()
      if (mainWindow.isVisible()) {
        if (currentConfig.UI.IfToTray) {
          mainWindow.setSkipTaskbar(true) // 隐藏任务栏图标
        }
        mainWindow.hide()
      } else {
        if (mainWindow.isMinimized()) {
          mainWindow.restore()
        }
        mainWindow.setSkipTaskbar(false) // 恢复任务栏图标
        mainWindow.show()
        mainWindow.focus()
      }
    }
  })
}

// 销毁托盘
function destroyTray() {
  if (tray) {
    tray.destroy()
    tray = null
  }
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

function installRendererSecurity(
  window: Electron.BrowserWindow,
  policy: RendererNavigationPolicy
): void {
  const guardNavigation = (event: Electron.Event, navigationUrl: string) => {
    if (isTrustedRendererNavigation(navigationUrl, policy)) {
      return
    }
    event.preventDefault()
    logger.warn('已阻止应用窗口导航到不受信任的地址')
  }

  window.webContents.on('will-navigate', guardNavigation)
  window.webContents.on('will-redirect', guardNavigation)
  window.webContents.setWindowOpenHandler(({ url }) => {
    const externalUrl = normalizeExternalNavigation(url)
    if (externalUrl) {
      void shell.openExternal(externalUrl).catch(error => {
        logger.warn(`无法在系统浏览器中打开外部链接: ${String(error)}`)
      })
    } else {
      logger.warn('已阻止应用窗口打开不受信任的子窗口地址')
    }
    return { action: 'deny' }
  })
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
      sandbox: true,
      backgroundThrottling: false, // 防止后台节流
    },
  })

  const devServer = getRendererDevServerUrl(app.isPackaged)
  const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
  installRendererSecurity(win, {
    devServerUrl: devServer,
    packagedHtmlPath: indexHtmlPath,
  })

  // 把局部的 win 赋值给模块级（供其他模块/函数用）
  mainWindow = win

  // Electron 在最大化窗口最小化后会让 isMaximized() 返回 false，单独记住恢复目标状态。
  let restoreToMaximized = Boolean(config.UI.maximized)
  win.on('maximize', () => {
    restoreToMaximized = true
  })
  win.on('unmaximize', () => {
    restoreToMaximized = false
  })
  win.on('restore', () => {
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
    }
  })

  win.webContents.on(
    'did-fail-load',
    (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      if (!isMainFrame) return
      logger.error(`页面加载失败: ${errorCode} ${errorDescription}, URL: ${validatedURL}`)
    }
  )

  win.webContents.on('preload-error', (_event, preloadPath, error) => {
    logger.error(`预加载脚本执行失败: ${preloadPath}, ${error.stack || error.message}`)
  })

  win.webContents.on('render-process-gone', (_event, details) => {
    logger.error(`渲染进程异常退出: ${details.reason}, exitCode: ${details.exitCode}`)
  })

  win.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    if (level < 2) return
    const source = sourceId ? `${sourceId}:${line}` : `line ${line}`
    const logMessage = `渲染进程控制台: ${message}, 来源: ${source}`
    if (level >= 3) {
      logger.error(logMessage)
    } else {
      logger.warn(logMessage)
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
  if (devServer) {
    logger.info(`加载开发服务器: ${devServer}`)
    win.loadURL(devServer)
  } else {
    logger.info(`加载生产环境页面: ${indexHtmlPath}`)
    win.loadFile(indexHtmlPath)
  }

  // 窗口事件处理
  win.on('close', (event: Electron.Event) => {
    const currentConfig = loadConfig()

    if (!isQuitting && currentConfig.UI.IfToTray) {
      event.preventDefault()
      win.hide()
      win.setSkipTaskbar(true)
      updateTrayVisibility(currentConfig)
      logger.info('窗口已最小化到托盘，任务栏图标已隐藏')
    } else {
      // 立即保存窗口状态，不使用防抖
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
    const currentConfig = loadConfig()
    if (currentConfig.UI.IfToTray) {
      win.hide()
      win.setSkipTaskbar(true)
      updateTrayVisibility(currentConfig)
      logger.info('窗口已最小化到托盘，任务栏图标已隐藏')
    }
  })

  win.on('show', () => {
    if (restoreToMaximized && !win.isMaximized() && !win.isMinimized()) {
      win.maximize()
    }
    const currentConfig = loadConfig()
    win.setSkipTaskbar(false)
    updateTrayVisibility(currentConfig)
    logger.info('窗口已显示，任务栏图标已恢复')
  })

  win.on('hide', () => {
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
  registerFileHandlers(() => mainWindow)
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
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    autoHideMenuBar: true,
    show: false,
  })

  const devServer = getRendererDevServerUrl(app.isPackaged)
  const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
  installRendererSecurity(logWindow, {
    devServerUrl: devServer,
    packagedHtmlPath: indexHtmlPath,
  })
  if (devServer) {
    logWindow.loadURL(`${devServer}#/logs`)
  } else {
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

      if (shouldDropHeartbeatProcessLog(level, moduleName, message)) {
        return
      }

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

ipcMain.handle('log:getContent', async (_event, lines?: number, fileName?: string) => {
  try {
    const appRoot = getAppRoot()
    const logPath = resolveDirectChildPath(path.join(appRoot, 'debug'), fileName, 'frontend.log')
    if (!logPath) {
      logger.warn('已拒绝读取日志目录外的文件')
      return ''
    }

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
  if (mainWindow) {
    isQuitting = true
    mainWindow.close()
  }
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
  isQuitting = true
  app.relaunch()
  app.quit()
})

// 添加强制退出处理器
ipcMain.handle('app-quit', () => {
  isQuitting = true
  app.quit()
})

// 添加进程管理相关的 IPC 处理器
ipcMain.handle('get-related-processes', async () => {
  try {
    return await getManagedBackendProcesses()
  } catch {
    logger.error('获取当前实例管理的后端进程失败')
    return []
  }
})

ipcMain.handle('kill-all-processes', async () => {
  const result = await cleanupInitializationResources()
  if (!result.success) {
    logger.warn(`安全停止后端失败: ${result.error}`)
  }
  return result
})

ipcMain.handle('window-is-maximized', () => {
  return mainWindow ? mainWindow.isMaximized() : false
})

// 在系统默认浏览器中打开URL
ipcMain.handle('open-url', async (_event, url: string) => {
  try {
    const externalUrl = normalizeExternalNavigation(url)
    if (!externalUrl) {
      throw new Error('Unsupported external URL')
    }
    await shell.openExternal(externalUrl)
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
    const resolvedPath = resolveRendererFilePath(filePath)
    if (!isSafeDocumentPath(resolvedPath) || !fs.statSync(resolvedPath).isFile()) {
      throw new Error('Only existing non-executable documents may be opened')
    }
    const openError = await shell.openPath(resolvedPath)
    if (openError) {
      throw new Error(openError)
    }
    return { success: true }
  } catch (error) {
    logger.error(`打开文件失败: ${error}`)
    return { success: false, error: error instanceof Error ? error.message : String(error) }
  }
})

// 显示文件所在目录并选中文件
ipcMain.handle('show-item-in-folder', async (_event, filePath: string) => {
  try {
    const resolvedPath = resolveRendererFilePath(filePath)
    if (!fs.existsSync(resolvedPath)) {
      throw new Error('File does not exist')
    }
    shell.showItemInFolder(resolvedPath)
    return { success: true }
  } catch (error) {
    logger.error(`显示文件所在目录失败: ${error}`)
    return { success: false, error: error instanceof Error ? error.message : String(error) }
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
  return isProcessElevated()
})

ipcMain.handle('restart-as-admin', async () => {
  return await restartAsAdmin()
})

// 应用生命周期
function registerApplicationLifecycle(): void {
  app.on('second-instance', (_event, commandLine, _workingDirectory, additionalData) => {
    const handoffData = additionalData as { elevationHandoffToken?: unknown }
    const suppliedToken =
      typeof handoffData.elevationHandoffToken === 'string'
        ? handoffData.elevationHandoffToken
        : readElevationHandoffToken(commandLine)
    if (pendingElevationHandoffToken && suppliedToken === pendingElevationHandoffToken) {
      logger.info('已确认管理员实例，完成旧实例清理后再交接单例锁')
      clearPendingElevationHandoff()
      isQuitting = true
      void completeElevationHandoff(
        async () => {
          await runShutdownCleanup()
          shutdownCleanupComplete = true
        },
        () => app.releaseSingleInstanceLock(),
        () => app.quit()
      )
      return
    }

    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore()
      }
      mainWindow.setSkipTaskbar(false)
      mainWindow.show()
      mainWindow.focus()
    }
  })

  app.on('before-quit', event => {
    if (shutdownCleanupComplete) {
      return
    }

    event.preventDefault()
    isQuitting = true
    if (shutdownCleanupStarted) {
      return
    }
    void runShutdownCleanup().finally(() => {
      shutdownCleanupComplete = true
      app.quit()
    })
  })

  void app.whenReady().then(() => {
    logger.info(`应用版本: ${app.getVersion()}`)
    logger.info(`Electron版本: ${process.versions.electron}`)
    logger.info(`Node版本: ${process.versions.node}`)
    logger.info(`平台: ${process.platform}`)

    const startupConfig = loadConfig()
    createWindow()

    setImmediate(() => {
      if (!isProcessElevated()) {
        logger.warn('应用未以管理员权限运行')
      } else {
        logger.info('应用以管理员权限运行')
      }
    })

    void prewarmBackend({
      currentVersion: app.getVersion(),
      initializedVersion:
        typeof startupConfig.initializedVersion === 'string'
          ? startupConfig.initializedVersion
          : null,
      autoUpdateEnabled: Boolean(startupConfig.Update?.IfAutoUpdate),
    }).catch(error => {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`生命周期后端预热失败，将由初始化流程处理: ${errorMsg}`)
    })
  })

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      isQuitting = true
      app.quit()
    }
  })

  app.on('activate', () => {
    if (mainWindow === null) createWindow()
  })
}

void waitForSingleInstanceLock({
  commandLine: process.argv,
  requestLock: additionalData => app.requestSingleInstanceLock(additionalData),
  timeoutMs: ELEVATION_HANDOFF_TIMEOUT_MS,
}).then(gotTheLock => {
  if (!gotTheLock) {
    app.quit()
    process.exit(0)
  }
  registerApplicationLifecycle()
})
