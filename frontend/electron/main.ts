import { app, BrowserWindow, ipcMain, dialog, shell, Tray, Menu, nativeImage } from 'electron'
import * as path from 'path'
import * as fs from 'fs'
import { spawn } from 'child_process'
import { getAppRoot, checkEnvironment } from './services/environmentService'
import { setMainWindow as setDownloadMainWindow } from './services/downloadService'
import {
  setMainWindow as setPythonMainWindow,
  downloadPython,
  installPipPackage,
  installDependencies,
  startBackend,
  stopBackend,
} from './services/pythonService'
import { setMainWindow as setGitMainWindow, downloadGit, cloneBackend } from './services/gitService'
import { setupLogger, log, getLogPath, getLogFiles, cleanOldLogs } from './services/logService'

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

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false
let saveWindowStateTimeout: NodeJS.Timeout | null = null

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
    size: '1600,1000'
  },
  Start: {
    IfMinimizeDirectly: false,
    IfSelfStart: false
  }
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
    log.error('加载配置失败:', error)
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
    log.error('保存配置失败:', error)
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
    path.join(app.getAppPath(), 'dist/AUTO-MAS.ico')
  ]
  
  let trayIcon
  
  try {
    // 尝试加载图标
    for (const iconPath of iconPaths) {
      if (fs.existsSync(iconPath)) {
        trayIcon = nativeImage.createFromPath(iconPath)
        if (!trayIcon.isEmpty()) {
          log.info(`成功加载托盘图标: ${iconPath}`)
          break
        }
      }
    }
    
    // 如果所有路径都失败，创建一个默认图标
    if (!trayIcon || trayIcon.isEmpty()) {
      log.warn('无法加载托盘图标，使用默认图标')
      trayIcon = nativeImage.createEmpty()
    }
  } catch (error) {
    log.error('加载托盘图标失败:', error)
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
      }
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
      }
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        isQuitting = true
        app.quit()
      }
    }
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
    log.warn('防幽灵机制：强制显示托盘图标')
  }

  if (shouldShowTray && !tray) {
    createTray()
    log.info('托盘图标已创建')
  } else if (!shouldShowTray && tray) {
    destroyTray()
    log.info('托盘图标已销毁')
  }
}

function createWindow() {
  log.info('开始创建主窗口')
  
  const config = loadConfig()
  
  // 解析窗口大小
  const [width, height] = config.UI.size.split(',').map(s => parseInt(s.trim()) || 1600)
  const [x, y] = config.UI.location.split(',').map(s => parseInt(s.trim()) || 100)
  
  mainWindow = new BrowserWindow({
    width: Math.max(width, 800),
    height: Math.max(height, 600),
    x,
    y,
    minWidth: 800,
    minHeight: 600,
    icon: path.join(__dirname, '../public/AUTO-MAS.ico'),
    frame: false, // 去掉系统标题栏
    titleBarStyle: 'hidden', // 隐藏标题栏
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    autoHideMenuBar: true,
    show: !config.Start.IfMinimizeDirectly, // 根据配置决定是否直接显示
  })

  // 如果配置为最大化，则最大化窗口
  if (config.UI.maximized) {
    mainWindow.maximize()
  }

  mainWindow.setMenuBarVisibility(false)
  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    log.info(`加载开发服务器: ${devServer}`)
    mainWindow.loadURL(devServer)
  } else {
    const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
    log.info(`加载生产环境页面: ${indexHtmlPath}`)
    mainWindow.loadFile(indexHtmlPath)
  }

  // 窗口事件处理
  mainWindow.on('close', (event) => {
    const currentConfig = loadConfig()
    
    if (!isQuitting && currentConfig.UI.IfToTray) {
      // 如果启用了最小化到托盘，阻止关闭并隐藏窗口
      event.preventDefault()
      mainWindow?.hide()
      mainWindow?.setSkipTaskbar(true)
      
      // 更新托盘状态
      updateTrayVisibility(currentConfig)
      
      log.info('窗口已最小化到托盘，任务栏图标已隐藏')
    } else {
      // 保存窗口状态
      saveWindowState()
    }
  })

  mainWindow.on('closed', () => {
    log.info('主窗口已关闭')
    mainWindow = null
  })

  // 窗口最小化事件
  mainWindow.on('minimize', () => {
    const currentConfig = loadConfig()
    
    if (currentConfig.UI.IfToTray) {
      // 如果启用了最小化到托盘，隐藏窗口并从任务栏移除
      mainWindow?.hide()
      mainWindow?.setSkipTaskbar(true)
      
      // 更新托盘状态
      updateTrayVisibility(currentConfig)
      
      log.info('窗口已最小化到托盘，任务栏图标已隐藏')
    }
  })

  // 窗口显示/隐藏事件，用于更新托盘状态
  mainWindow.on('show', () => {
    const currentConfig = loadConfig()
    // 窗口显示时，恢复任务栏图标
    mainWindow?.setSkipTaskbar(false)
    updateTrayVisibility(currentConfig)
    log.info('窗口已显示，任务栏图标已恢复')
  })

  mainWindow.on('hide', () => {
    const currentConfig = loadConfig()
    // 窗口隐藏时，根据配置决定是否隐藏任务栏图标
    if (currentConfig.UI.IfToTray) {
      mainWindow?.setSkipTaskbar(true)
      log.info('窗口已隐藏，任务栏图标已隐藏')
    }
    updateTrayVisibility(currentConfig)
  })

  // 窗口移动和调整大小时保存状态
  mainWindow.on('moved', saveWindowState)
  mainWindow.on('resized', saveWindowState)
  mainWindow.on('maximize', saveWindowState)
  mainWindow.on('unmaximize', saveWindowState)

  // 设置各个服务的主窗口引用
  if (mainWindow) {
    setDownloadMainWindow(mainWindow)
    setPythonMainWindow(mainWindow)
    setGitMainWindow(mainWindow)
    log.info('主窗口创建完成，服务引用已设置')
  }

  // 根据配置初始化托盘
  updateTrayVisibility(config)
}

// 保存窗口状态（带防抖）
function saveWindowState() {
  if (!mainWindow) return
  
  // 清除之前的定时器
  if (saveWindowStateTimeout) {
    clearTimeout(saveWindowStateTimeout)
  }
  
  // 设置新的定时器，500ms后保存
  saveWindowStateTimeout = setTimeout(() => {
    try {
      const config = loadConfig()
      const bounds = mainWindow!.getBounds()
      const isMaximized = mainWindow!.isMaximized()
      
      // 只有在窗口不是最大化状态时才保存位置和大小
      if (!isMaximized) {
        config.UI.size = `${bounds.width},${bounds.height}`
        config.UI.location = `${bounds.x},${bounds.y}`
      }
      config.UI.maximized = isMaximized
      
      saveConfig(config)
      log.info('窗口状态已保存')
    } catch (error) {
      log.error('保存窗口状态失败:', error)
    }
  }, 500)
}

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
    mainWindow.close()
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
      console.error('打开链接失败:', error.message)
      return { success: false, error: error.message }
    } else {
      console.error('未知错误:', error)
      return { success: false, error: String(error) }
    }
  }
})

// 打开文件
ipcMain.handle('open-file', async (_event, filePath: string) => {
  try {
    await shell.openPath(filePath)
  } catch (error) {
    console.error('打开文件失败:', error)
    throw error
  }
})

// 显示文件所在目录并选中文件
ipcMain.handle('show-item-in-folder', async (_event, filePath: string) => {
  try {
    shell.showItemInFolder(filePath)
  } catch (error) {
    console.error('显示文件所在目录失败:', error)
    throw error
  }
})

// 环境检查
ipcMain.handle('check-environment', async () => {
  const appRoot = getAppRoot()
  return checkEnvironment(appRoot)
})

// Python相关
ipcMain.handle('download-python', async (_event, mirror = 'tsinghua') => {
  const appRoot = getAppRoot()
  return downloadPython(appRoot, mirror)
})

ipcMain.handle('install-pip', async () => {
  const appRoot = getAppRoot()
  return installPipPackage(appRoot)
})

ipcMain.handle('install-dependencies', async (_event, mirror = 'tsinghua') => {
  const appRoot = getAppRoot()
  return installDependencies(appRoot, mirror)
})

ipcMain.handle('start-backend', async () => {
  const appRoot = getAppRoot()
  return startBackend(appRoot)
})

ipcMain.handle('stop-backend', async () => {
  return stopBackend()
})

// Git相关
ipcMain.handle('download-git', async () => {
  const appRoot = getAppRoot()
  return downloadGit(appRoot)
})

ipcMain.handle(
  'clone-backend',
  async (_event, repoUrl = 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git') => {
    const appRoot = getAppRoot()
    return cloneBackend(appRoot, repoUrl)
  }
)

ipcMain.handle(
  'update-backend',
  async (_event, repoUrl = 'https://github.com/AUTO-MAS-Project/AUTO-MAS.git') => {
    const appRoot = getAppRoot()
    return cloneBackend(appRoot, repoUrl) // 使用相同的逻辑，会自动判断是pull还是clone
  }
)

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
    console.log(`配置已保存到: ${configPath}`)
    
    // 如果是UI配置更新，需要更新托盘状态
    if (config.UI) {
      updateTrayVisibility(config)
    }
  } catch (error) {
    console.error('保存配置文件失败:', error)
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
    
    log.info('托盘设置已更新:', uiSettings)
    return true
  } catch (error) {
    log.error('更新托盘设置失败:', error)
    throw error
  }
})

ipcMain.handle('load-config', async () => {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (fs.existsSync(configPath)) {
      const config = fs.readFileSync(configPath, 'utf8')
      console.log(`从文件加载配置: ${configPath}`)
      return JSON.parse(config)
    }

    return null
  } catch (error) {
    console.error('加载配置文件失败:', error)
    return null
  }
})

ipcMain.handle('reset-config', async () => {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (fs.existsSync(configPath)) {
      fs.unlinkSync(configPath)
      console.log(`配置文件已删除: ${configPath}`)
    }
  } catch (error) {
    console.error('重置配置文件失败:', error)
    throw error
  }
})

// 日志文件操作
ipcMain.handle('get-log-path', async () => {
  try {
    return getLogPath()
  } catch (error) {
    log.error('获取日志路径失败:', error)
    throw error
  }
})

ipcMain.handle('get-log-files', async (_event) => {
  try {
    return getLogFiles()
  } catch (error) {
    log.error('获取日志文件列表失败:', error)
    throw error
  }
})

ipcMain.handle('get-logs', async (_event, lines?: number, fileName?: string) => {
  try {
    let logFilePath: string
    
    if (fileName) {
      // 如果指定了文件名，使用指定的文件
      const appRoot = getAppRoot()
      logFilePath = path.join(appRoot, 'logs', fileName)
    } else {
      // 否则使用当前日志文件
      logFilePath = getLogPath()
    }
    
    if (!fs.existsSync(logFilePath)) {
      return ''
    }

    const logs = fs.readFileSync(logFilePath, 'utf8')
    
    if (lines && lines > 0) {
      const logLines = logs.split('\n')
      return logLines.slice(-lines).join('\n')
    }
    
    return logs
  } catch (error) {
    log.error('读取日志文件失败:', error)
    throw error
  }
})

ipcMain.handle('clear-logs', async (_event, fileName?: string) => {
  try {
    let logFilePath: string
    
    if (fileName) {
      // 如果指定了文件名，清空指定的文件
      const appRoot = getAppRoot()
      logFilePath = path.join(appRoot, 'logs', fileName)
    } else {
      // 否则清空当前日志文件
      logFilePath = getLogPath()
    }
    
    if (fs.existsSync(logFilePath)) {
      fs.writeFileSync(logFilePath, '', 'utf8')
      log.info(`日志文件已清空: ${fileName || '当前文件'}`)
    }
  } catch (error) {
    log.error('清空日志文件失败:', error)
    throw error
  }
})

ipcMain.handle('clean-old-logs', async (_event, daysToKeep = 7) => {
  try {
    cleanOldLogs(daysToKeep)
    log.info(`已清理${daysToKeep}天前的旧日志文件`)
  } catch (error) {
    log.error('清理旧日志文件失败:', error)
    throw error
  }
})

// 保留原有的日志操作方法以兼容现有代码
ipcMain.handle('save-logs-to-file', async (_event, logs: string) => {
  try {
    const appRoot = getAppRoot()
    const logsDir = path.join(appRoot, 'logs')

    // 确保logs目录存在
    if (!fs.existsSync(logsDir)) {
      fs.mkdirSync(logsDir, { recursive: true })
    }

    const logFilePath = path.join(logsDir, 'app.log')
    fs.writeFileSync(logFilePath, logs, 'utf8')
    log.info(`日志已保存到: ${logFilePath}`)
  } catch (error) {
    log.error('保存日志文件失败:', error)
    throw error
  }
})

ipcMain.handle('load-logs-from-file', async () => {
  try {
    const appRoot = getAppRoot()
    const logFilePath = path.join(appRoot, 'logs', 'app.log')

    if (fs.existsSync(logFilePath)) {
      const logs = fs.readFileSync(logFilePath, 'utf8')
      log.info(`从文件加载日志: ${logFilePath}`)
      return logs
    }

    return null
  } catch (error) {
    log.error('加载日志文件失败:', error)
    return null
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

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  }
})

app.on('before-quit', async event => {
  // 只处理一次，避免多重触发
  if (!isQuitting) {
    event.preventDefault()
    isQuitting = true
    
    log.info('应用准备退出')
    
    // 清理托盘
    destroyTray()
    
    try {
      await stopBackend()
      log.info('后端服务已停止')
    } catch (e) {
      log.error('停止后端时出错:', e)
      console.error('停止后端时出错:', e)
    } finally {
      log.info('应用退出')
      app.exit(0)
    }
  }
})

app.whenReady().then(() => {
  // 初始化日志系统
  setupLogger()
  
  // 清理7天前的旧日志
  cleanOldLogs(7)
  
  log.info('应用启动')
  log.info(`应用版本: ${app.getVersion()}`)
  log.info(`Electron版本: ${process.versions.electron}`)
  log.info(`Node版本: ${process.versions.node}`)
  log.info(`平台: ${process.platform}`)
  
  // 检查管理员权限
  if (!isRunningAsAdmin()) {
    log.warn('应用未以管理员权限运行')
    console.log('应用未以管理员权限运行')
    // 在生产环境中，可以选择是否强制要求管理员权限
    // 这里先创建窗口，让用户选择是否重新启动
  } else {
    log.info('应用以管理员权限运行')
  }
  
  createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})
