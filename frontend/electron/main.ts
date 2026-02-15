import { exec, spawn } from 'child_process'
import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, nativeTheme, screen, shell, Tray, } from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import { checkEnvironment, getAppRoot } from './services/environmentService'
import { cleanupInitializationResources, registerInitializationHandlers, } from './ipc/initializationHandlers'
import { registerFileHandlers } from './ipc/fileHandlers'

import { getLogger, initializeLogger } from './services/logger'
import AdmZip = require('adm-zip')

// 初始化日志系统（必须在创建 logger 之前）
initializeLogger()

const logger = getLogger('主进程')

// 强制清理相关进程的函数
async function forceKillRelatedProcesses(): Promise<void> {
  try {
    const { killAllRelatedProcesses } = await import('./utils/processManager')
    await killAllRelatedProcesses()
    logger.info('所有相关进程已清理')
  } catch (error) {
    logger.error(`清理进程时出错: ${error}`)

    // 备用清理方法
    if (process.platform === 'win32') {
      const appRoot = getAppRoot()
      const pythonExePath = path.join(appRoot, 'environment', 'python', 'python.exe')

      return new Promise(resolve => {
        // 使用更简单的命令强制结束相关进程
        exec(`taskkill /f /im python.exe`, error => {
          if (error) {
            logger.warn(`备用清理方法失败: ${error.message}`)
          } else {
            logger.info('备用清理方法执行成功')
          }
          resolve()
        })
      })
    }
  }
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
let isQuitting = false
let saveWindowStateTimeout: NodeJS.Timeout | null = null
let isInitialStartup = true // 标记是否为初次启动

// 配置接口
interface AppConfig {
  UI: {
    IfShowTray: boolean
    IfToTray: boolean
    location: string
    maximized: boolean
    size: string
  }
  Start: {
    IfMinimizeDirectly: boolean
    IfSelfStart: boolean
  }

  [key: string]: any
}

// 默认配置
const defaultConfig: AppConfig = {
  UI: {
    IfShowTray: false,
    IfToTray: false,
    location: '100,100',
    maximized: false,
    size: '1600,1000',
  },
  Start: {
    IfMinimizeDirectly: false,
    IfSelfStart: false,
  },
}

// 加载配置
function loadConfig(): AppConfig {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (fs.existsSync(configPath)) {
      const configData = fs.readFileSync(configPath, 'utf8')
      const config = JSON.parse(configData)
      return { ...defaultConfig, ...config }
    }
  } catch (error) {
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
  } catch (error) {
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
  } catch (error) {
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

function createWindow() {
  logger.info('开始创建主窗口')

  const config = loadConfig()

  // 解析配置
  const [cfgW, cfgH] = config.UI.size.split(',').map((s: string) => parseInt(s.trim(), 10) || 1600)
  const [cfgX, cfgY] = config.UI.location
    .split(',')
    .map((s: string) => parseInt(s.trim(), 10) || 100)

  // 以目标位置选最近显示器
  const targetDisplay = screen.getDisplayNearestPoint({ x: cfgX, y: cfgY })
  const sf = targetDisplay.scaleFactor

  // 逻辑最小尺寸（DIP）
  const minDipW = Math.floor(1600 / sf)
  const minDipH = Math.floor(900 / sf)

  // 初始窗口逻辑尺寸（DIP）
  let initW = Math.max(cfgW, minDipW)
  let initH = Math.max(cfgH, minDipH)

  // 不超过工作区
  const { width: waW, height: waH } = targetDisplay.workAreaSize
  initW = Math.min(initW, waW)
  initH = Math.min(initH, waH)

  // 关键：用局部常量 win，全程用它，类型不为 null
  const win = new BrowserWindow({
    x: cfgX,
    y: cfgY,
    width: initW,
    height: initH,
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

  // 页面加载完成后再显示窗口，避免白屏闪烁
  win.webContents.on('did-finish-load', () => {
    // 根据配置决定是否显示窗口
    if (!config.Start.IfMinimizeDirectly) {
      win.show()
      logger.info('页面加载完成，窗口已显示')
    }
  })

  // 根据显示器动态更新最小尺寸/边界
  const recomputeMinSize = () => {
    // 这里用 win，不会是 null
    const bounds = win.getBounds()
    const disp = screen.getDisplayMatching(bounds)
    const s = disp.scaleFactor
    const w = Math.floor(1600 / s)
    const h = Math.floor(900 / s)

    const [curMinW, curMinH] = win.getMinimumSize()
    if (w !== curMinW || h !== curMinH) {
      win.setMinimumSize(w, h)

      if (win.isMaximized()) return

      const { width: wW, height: wH } = disp.workAreaSize
      const newBounds = { ...bounds }
      if (newBounds.width > wW) newBounds.width = wW
      if (newBounds.height > wH) newBounds.height = wH
      if (newBounds.width < w) newBounds.width = w
      if (newBounds.height < h) newBounds.height = h
      win.setBounds(newBounds)
    }
  }

  // 监听显示器变化/窗口移动
  win.on('moved', recomputeMinSize)
  win.on('resized', recomputeMinSize)
  screen.on('display-metrics-changed', recomputeMinSize)

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
          const bounds = win.getBounds()
          const isMaximized = win.isMaximized()

          if (!isMaximized) {
            config.UI.size = `${bounds.width},${bounds.height}`
            config.UI.location = `${bounds.x},${bounds.y}`
          }
          config.UI.maximized = isMaximized

          saveConfig(config)
          logger.info('窗口状态已保存')
        } catch (error) {
          logger.error('保存窗口状态失败')
        }
      }
    }
  })

  win.on('closed', () => {
    logger.info('主窗口已关闭')
    // 清理监听（可选）
    screen.removeListener('display-metrics-changed', recomputeMinSize)
    // 置空模块级引用
    mainWindow = null

    // 如果是正在退出，立即执行进程清理
    if (isQuitting) {
      logger.info('窗口关闭，执行最终清理')
      setTimeout(async () => {
        try {
          await forceKillRelatedProcesses()
        } catch (e) {
          logger.error('最终清理失败')
        }
        process.exit(0)
      }, 100)
    }
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
          const bounds = win.getBounds()
          const isMaximized = win.isMaximized()

          if (!isMaximized) {
            config.UI.size = `${bounds.width},${bounds.height}`
            config.UI.location = `${bounds.x},${bounds.y}`
          }
          config.UI.maximized = isMaximized

          saveConfig(config)
          logger.info('窗口状态已自动保存')
        } catch (error) {
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

  // 初始托盘配置（使用文件配置）
  updateTrayVisibility(config)

  // 等待窗口准备完成后再初始化托盘和处理启动配置
  win.webContents.once('did-finish-load', () => {
    // 重新加载配置以确保获取最新配置
    const currentConfig = loadConfig()

    // 根据配置初始化托盘
    updateTrayVisibility(currentConfig)

    // 处理启动后直接最小化（只在初次启动时执行）
    if (isInitialStartup && currentConfig.Start.IfMinimizeDirectly) {
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
  app.exit(0)
})

// 添加强制退出处理器
ipcMain.handle('app-quit', () => {
  isQuitting = true
  app.quit()
})

// 添加进程管理相关的 IPC 处理器
ipcMain.handle('get-related-processes', async () => {
  try {
    const { getRelatedProcesses } = await import('./utils/processManager')
    return await getRelatedProcesses()
  } catch (error) {
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
  } catch (error) {
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
      } catch (error) {
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
  } catch (error) {
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
  } catch (error) {
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
      } catch (error) {
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
  } catch (error) {
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
  } catch (error) {
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

app.on('before-quit', async event => {
  // 只处理一次，避免多重触发
  if (!isQuitting) {
    event.preventDefault()
    isQuitting = true

    logger.info('应用准备退出')

    // 清理定时器
    if (saveWindowStateTimeout) {
      clearTimeout(saveWindowStateTimeout)
      saveWindowStateTimeout = null
    }

    // 清理托盘
    destroyTray()

    // 清理初始化资源
    try {
      await cleanupInitializationResources()
      logger.info('初始化资源清理完成')
    } catch (e) {
      logger.error('资源清理失败')
    }

    // 立即开始强制清理，不等待优雅关闭
    logger.info('开始强制清理所有相关进程')

    try {
      // 并行执行多种清理方法
      const cleanupPromises = [
        // 方法1: 使用我们的进程管理器
        forceKillRelatedProcesses(),

        // 方法2: 直接使用 taskkill 和 PowerShell 命令
        new Promise<void>(resolve => {
          if (process.platform === 'win32') {
            const appRoot = getAppRoot()
            const escapedAppRoot = appRoot.replace(/\\/g, '\\\\')
            const commands = [
              `taskkill /f /im python.exe`,
              // 使用 PowerShell 代替 wmic
              `powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"`,
              `powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*${escapedAppRoot}*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"`,
            ]

            let completed = 0
            commands.forEach(cmd => {
              exec(cmd, () => {
                completed++
                if (completed === commands.length) {
                  resolve()
                }
              })
            })

            // 2秒超时
            setTimeout(resolve, 2000)
          } else {
            resolve()
          }
        }),
      ]

      // 最多等待3秒
      const timeoutPromise = new Promise(resolve => setTimeout(resolve, 3000))
      await Promise.race([Promise.all(cleanupPromises), timeoutPromise])

      logger.info('进程清理完成')
    } catch (e) {
      logger.error('进程清理时出错')
    }

    logger.info('应用强制退出')

    // 使用 process.exit 而不是 app.exit，更加强制
    setTimeout(() => {
      process.exit(0)
    }, 500)
  }
})

app.whenReady().then(async () => {
  logger.info(`应用版本: ${app.getVersion()}`)
  logger.info(`Electron版本: ${process.versions.electron}`)
  logger.info(`Node版本: ${process.versions.node}`)
  logger.info(`平台: ${process.platform}`)

  // 注册文件操作处理器（在窗口创建之前注册）
  registerFileHandlers()
  logger.info('文件操作处理器已注册')

  // 检查管理员权限
  if (!isRunningAsAdmin()) {
    logger.warn('应用未以管理员权限运行')
    // 在生产环境中，可以选择是否强制要求管理员权限
    // 这里先创建窗口，让用户选择是否重新启动
  } else {
    logger.info('应用以管理员权限运行')
  }

  createWindow()
})

app.on('window-all-closed', async () => {
  if (process.platform !== 'darwin') {
    isQuitting = true

    app.quit()
  }
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})
