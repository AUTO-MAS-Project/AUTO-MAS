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
} from 'electron'
import * as path from 'path'
import * as fs from 'fs'
import { exec, spawn } from 'child_process'
import { checkEnvironment, getAppRoot } from './services/environmentService'
import { setMainWindow as setDownloadMainWindow } from './services/downloadService'
import {
  downloadPython,
  installDependencies,
  installPipPackage,
  setMainWindow as setPythonMainWindow,
  startBackend,
} from './services/pythonService'
import {
  cloneBackend,
  downloadGit,
  setMainWindow as setGitMainWindow,
  checkRepoStatus,
  cleanDepot,
  getRepoInfo,
} from './services/gitService'
import { cleanOldLogs, getLogFiles, getLogPath, log, setupLogger } from './services/logService'

// 强制清理相关进程的函数
async function forceKillRelatedProcesses(): Promise<void> {
  try {
    const { killAllRelatedProcesses } = await import('./utils/processManager')
    await killAllRelatedProcesses()
    log.info('所有相关进程已清理')
  } catch (error) {
    log.error('清理进程时出错:', error)

    // 备用清理方法
    if (process.platform === 'win32') {
      const appRoot = getAppRoot()
      const pythonExePath = path.join(appRoot, 'environment', 'python', 'python.exe')

      return new Promise(resolve => {
        // 使用更简单的命令强制结束相关进程
        exec(`taskkill /f /im python.exe`, error => {
          if (error) {
            log.warn('备用清理方法失败:', error.message)
          } else {
            log.info('备用清理方法执行成功')
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
    path.join(app.getAppPath(), 'dist/AUTO-MAS.ico'),
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

let mainWindow: Electron.BrowserWindow | null = null

function createWindow() {
  log.info('开始创建主窗口')

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
    show: !config.Start.IfMinimizeDirectly,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  // 把局部的 win 赋值给模块级（供其他模块/函数用）
  mainWindow = win

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
    log.info(`加载开发服务器: ${devServer}`)
    win.loadURL(devServer)
  } else {
    const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
    log.info(`加载生产环境页面: ${indexHtmlPath}`)
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
      log.info('窗口已最小化到托盘，任务栏图标已隐藏')
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
          log.info('窗口状态已保存')
        } catch (error) {
          log.error('保存窗口状态失败:', error)
        }
      }
    }
  })

  win.on('closed', () => {
    log.info('主窗口已关闭')
    // 清理监听（可选）
    screen.removeListener('display-metrics-changed', recomputeMinSize)
    // 置空模块级引用
    mainWindow = null

    // 如果是正在退出，立即执行进程清理
    if (isQuitting) {
      log.info('窗口关闭，执行最终清理')
      setTimeout(async () => {
        try {
          await forceKillRelatedProcesses()
        } catch (e) {
          log.error('最终清理失败:', e)
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
      log.info('窗口已最小化到托盘，任务栏图标已隐藏')
    }
  })

  win.on('show', () => {
    const currentConfig = loadConfig()
    win.setSkipTaskbar(false)
    updateTrayVisibility(currentConfig)
    log.info('窗口已显示，任务栏图标已恢复')
  })

  win.on('hide', () => {
    const currentConfig = loadConfig()
    if (currentConfig.UI.IfToTray) {
      win.setSkipTaskbar(true)
      log.info('窗口已隐藏，任务栏图标已隐藏')
    }
    updateTrayVisibility(currentConfig)
  })

  // 移动/调整大小/最大化状态变化时保存
  win.on('moved', saveWindowState)
  win.on('resized', saveWindowState)
  win.on('maximize', saveWindowState)
  win.on('unmaximize', saveWindowState)

  // 设置各个服务的主窗口引用（此处 win 一定存在，可直接传）
  setDownloadMainWindow(win)
  setPythonMainWindow(win)
  setGitMainWindow(win)
  log.info('主窗口创建完成，服务引用已设置')

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
        log.info('应用初次启动后直接最小化到托盘')
      } else {
        win.minimize()
        log.info('应用初次启动后直接最小化')
      }
      updateTrayVisibility(currentConfig)
    }

    // 标记初次启动已完成
    isInitialStartup = false
  })
}

// 保存窗口状态（带防抖）
function saveWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return

  // 清除之前的定时器
  if (saveWindowStateTimeout) {
    clearTimeout(saveWindowStateTimeout)
  }

  // 设置新的定时器，500ms后保存
  saveWindowStateTimeout = setTimeout(() => {
    try {
      // 再次检查窗口是否存在且未销毁
      if (!mainWindow || mainWindow.isDestroyed()) {
        log.warn('窗口已销毁，跳过保存状态')
        return
      }

      const config = loadConfig()
      const bounds = mainWindow.getBounds()
      const isMaximized = mainWindow.isMaximized()

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
    isQuitting = true
    mainWindow.close()
  }
})

// 添加应用重启处理器
ipcMain.handle('app-restart', () => {
  console.log('重启应用程序...')
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
    log.error('获取进程信息失败:', error)
    return []
  }
})

ipcMain.handle('kill-all-processes', async () => {
  try {
    await forceKillRelatedProcesses()
    return { success: true }
  } catch (error) {
    log.error('强制清理进程失败:', error)
    return { success: false, error: error instanceof Error ? error.message : String(error) }
  }
})

// 添加一个测试用的强制退出命令
ipcMain.handle('force-exit', async () => {
  log.info('收到强制退出命令')
  isQuitting = true

  // 立即清理进程
  try {
    await forceKillRelatedProcesses()
  } catch (e) {
    log.error('强制清理失败:', e)
  }

  // 强制退出
  setTimeout(() => {
    process.exit(0)
  }, 500)

  return { success: true }
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

    log.info('关键文件检查结果:', result)
    return result
  } catch (error) {
    log.error('检查关键文件失败:', error)
    return {
      pythonExists: false,
      pipExists: false,
      gitExists: false,
      mainPyExists: false,
    }
  }
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
  const { stopBackend } = await import('./services/pythonService')
  return stopBackend()
})

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
        log.warn('读取主题配置失败，使用默认值:', error)
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
    log.error('获取主题信息失败:', error)
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
        log.warn('读取主题配置失败，使用默认值:', error)
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
    log.error('获取对话框主题失败:', error)
    return nativeTheme.shouldUseDarkColors ? 'dark' : 'light'
  }
})

// 全局存储对话框窗口引用和回调
let dialogWindows = new Map<string, BrowserWindow>()
let dialogCallbacks = new Map<string, (result: boolean) => void>()

// 创建对话框窗口
function createQuestionDialog(questionData: any): Promise<boolean> {
  return new Promise(resolve => {
    const messageId = questionData.messageId || 'dialog_' + Date.now()

    // 存储回调函数
    dialogCallbacks.set(messageId, resolve)

    // 准备对话框数据
    const dialogData = {
      title: questionData.title || '操作确认',
      message: questionData.message || '是否要执行此操作？',
      options: questionData.options || ['确定', '取消'],
      messageId: messageId,
    }

    // 获取主窗口的尺寸用于全屏显示
    let windowBounds = { width: 800, height: 600, x: 100, y: 100 }
    if (mainWindow && !mainWindow.isDestroyed()) {
      windowBounds = mainWindow.getBounds()
    }

    // 创建对话框窗口 - 小尺寸可拖动窗口
    const dialogWindow = new BrowserWindow({
      width: 400,
      height: 145,
      x: windowBounds.x + (windowBounds.width - 400) / 2, // 居中显示
      y: windowBounds.y + (windowBounds.height - 200) / 2,
      resizable: false, // 不允许改变大小
      minimizable: false,
      maximizable: false,
      alwaysOnTop: true,
      show: false,
      frame: false,
      modal: mainWindow ? true : false,
      parent: mainWindow || undefined,
      icon: path.join(__dirname, '../public/AUTO-MAS.ico'),
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        preload: path.join(__dirname, 'preload.js'),
      },
    })

    // 存储窗口引用
    dialogWindows.set(messageId, dialogWindow)

    // 编码对话框数据
    const encodedData = encodeURIComponent(JSON.stringify(dialogData))

    // 加载对话框页面
    const dialogUrl = `file://${path.join(__dirname, '../public/dialog.html')}?data=${encodedData}`
    dialogWindow.loadURL(dialogUrl)

    // 窗口准备好后显示
    dialogWindow.once('ready-to-show', () => {
      dialogWindow.show()
      dialogWindow.focus()
    })

    // 窗口关闭时清理
    dialogWindow.on('closed', () => {
      dialogWindows.delete(messageId)
      const callback = dialogCallbacks.get(messageId)
      if (callback) {
        dialogCallbacks.delete(messageId)
        callback(false) // 默认返回 false (取消)
      }
    })

    log.info(`全屏对话框窗口已创建: ${messageId}`)
  })
}

// 显示问题对话框
ipcMain.handle('show-question-dialog', async (_event, questionData) => {
  log.info('收到显示对话框请求:', questionData)
  try {
    const result = await createQuestionDialog(questionData)
    log.info(`对话框结果: ${result}`)
    return result
  } catch (error) {
    log.error('创建对话框失败:', error)
    return false
  }
})

// 处理对话框响应
ipcMain.handle('dialog-response', async (_event, messageId: string, choice: boolean) => {
  log.info(`收到对话框响应: ${messageId} = ${choice}`)

  const callback = dialogCallbacks.get(messageId)
  if (callback) {
    dialogCallbacks.delete(messageId)
    callback(choice)
  }

  // 关闭对话框窗口
  const dialogWindow = dialogWindows.get(messageId)
  if (dialogWindow && !dialogWindow.isDestroyed()) {
    dialogWindow.close()
  }
  dialogWindows.delete(messageId)

  return true
})

// 移动对话框窗口
ipcMain.handle('move-window', async (_event, deltaX: number, deltaY: number) => {
  // 获取当前活动的对话框窗口（最后创建的）
  const dialogWindow = Array.from(dialogWindows.values()).pop()
  if (dialogWindow && !dialogWindow.isDestroyed()) {
    const currentBounds = dialogWindow.getBounds()
    dialogWindow.setPosition(currentBounds.x + deltaX, currentBounds.y + deltaY)
  }
})

// Git相关
ipcMain.handle('download-git', async () => {
  const appRoot = getAppRoot()
  return downloadGit(appRoot)
})

// 新增的git管理方法
ipcMain.handle('check-repo-status', async () => {
  const appRoot = getAppRoot()
  const { checkRepoStatus } = await import('./services/gitService')
  return checkRepoStatus(appRoot)
})

ipcMain.handle('clean-depot', async () => {
  const appRoot = getAppRoot()
  const { cleanDepot } = await import('./services/gitService')
  return cleanDepot(appRoot)
})

ipcMain.handle('get-repo-info', async () => {
  const appRoot = getAppRoot()
  const { getRepoInfo } = await import('./services/gitService')
  return getRepoInfo(appRoot)
})

ipcMain.handle('check-git-update', async () => {
  try {
    const appRoot = getAppRoot()
    const repoPath = path.join(appRoot, 'repo')

    // 检查repo是否为Git仓库
    const gitDir = path.join(repoPath, '.git')
    if (!fs.existsSync(gitDir)) {
      log.info('repo不存在或不是Git仓库，需要重新克隆')
      return { hasUpdate: true, needsClone: true }
    }

    // 检查Git可执行文件是否存在
    const gitPath = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')
    if (!fs.existsSync(gitPath)) {
      log.warn('Git可执行文件不存在，需要先安装Git')
      return { hasUpdate: false, error: 'Git可执行文件不存在' }
    }

    // 获取Git环境变量
    const gitEnv = {
      ...process.env,
      PATH: `${path.join(appRoot, 'environment', 'git', 'bin')};${path.join(appRoot, 'environment', 'git', 'mingw64', 'bin')};${path.join(appRoot, 'environment', 'git', 'mingw64', 'libexec', 'git-core')};${process.env.PATH}`,
      GIT_EXEC_PATH: path.join(appRoot, 'environment', 'git', 'mingw64', 'libexec', 'git-core'),
      HOME: process.env.USERPROFILE || process.env.HOME,
      GIT_CONFIG_NOSYSTEM: '1',
      GIT_TERMINAL_PROMPT: '0',
      GIT_ASKPASS: '',
    }

    log.info('检查repo中的Git仓库状态...')

    // 获取当前分支名和commit hash
    const [currentBranch, currentCommit] = await Promise.all([
      new Promise<string>((resolve, reject) => {
        const branchProc = spawn(gitPath, ['branch', '--show-current'], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        let output = ''
        branchProc.stdout?.on('data', data => {
          output += data.toString()
        })
        branchProc.on('close', code => {
          if (code === 0) {
            resolve(output.trim())
          } else {
            resolve('unknown') // 如果获取失败，使用默认值
          }
        })
        branchProc.on('error', () => resolve('unknown'))
      }),
      new Promise<string>((resolve, reject) => {
        const commitProc = spawn(gitPath, ['rev-parse', 'HEAD'], {
          stdio: 'pipe',
          env: gitEnv,
          cwd: repoPath,
        })
        let output = ''
        commitProc.stdout?.on('data', data => {
          output += data.toString()
        })
        commitProc.on('close', code => {
          if (code === 0) {
            resolve(output.trim())
          } else {
            resolve('unknown')
          }
        })
        commitProc.on('error', () => resolve('unknown'))
      }),
    ])

    log.info(`当前repo状态 - 分支: ${currentBranch}, commit: ${currentCommit.substring(0, 8)}...`)

    // 由于我们使用镜像站更新，且新的更新逻辑会自动处理分支切换和代码同步，
    // 我们直接返回true让更新流程来处理一切
    log.info('返回hasUpdate=true，让更新流程处理分支切换和代码同步')
    return {
      hasUpdate: true,
      currentBranch,
      currentCommit: currentCommit.substring(0, 8),
      repoExists: true,
    }
  } catch (error) {
    log.error('检查Git更新失败:', error)
    // 如果检查失败，返回true以触发更新流程
    return { hasUpdate: true, error: error instanceof Error ? error.message : String(error) }
  }
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

    log.info('后端配置已同步:', backendSettings)
    return true
  } catch (error) {
    log.error('同步后端配置失败:', error)
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

ipcMain.handle('get-log-files', async _event => {
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

    // 清理定时器
    if (saveWindowStateTimeout) {
      clearTimeout(saveWindowStateTimeout)
      saveWindowStateTimeout = null
    }

    // 清理托盘
    destroyTray()

    // 立即开始强制清理，不等待优雅关闭
    log.info('开始强制清理所有相关进程')

    try {
      // 并行执行多种清理方法
      const cleanupPromises = [
        // 方法1: 使用我们的进程管理器
        forceKillRelatedProcesses(),

        // 方法2: 直接使用 taskkill 命令
        new Promise<void>(resolve => {
          if (process.platform === 'win32') {
            const appRoot = getAppRoot()
            const commands = [
              `taskkill /f /im python.exe`,
              `wmic process where "CommandLine like '%main.py%'" delete`,
              `wmic process where "CommandLine like '%${appRoot.replace(/\\/g, '\\\\')}%'" delete`,
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

      log.info('进程清理完成')
    } catch (e) {
      log.error('进程清理时出错:', e)
    }

    log.info('应用强制退出')

    // 使用 process.exit 而不是 app.exit，更加强制
    setTimeout(() => {
      process.exit(0)
    }, 500)
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
  if (process.platform !== 'darwin') {
    isQuitting = true
    app.quit()
  }
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})
