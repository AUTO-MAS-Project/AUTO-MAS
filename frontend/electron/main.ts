import { exec, spawn } from 'child_process'
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
import * as fs from 'fs'
import * as path from 'path'
import { checkEnvironment, getAppRoot } from './services/environmentService'
import { logService } from './services/logService'
import { registerInitializationHandlers, cleanupInitializationResources } from './ipc/initializationHandlers'
import { logManagementService } from './services/logManagementService'

// 强制清理相关进程的函数
async function forceKillRelatedProcesses(): Promise<void> {
  try {
    const { killAllRelatedProcesses } = await import('./utils/processManager')
    await killAllRelatedProcesses()
    logService.info('进程管理', '所有相关进程已清理')
  } catch (error) {
    logService.error('进程管理', `清理进程时出错: ${error}`)

    // 备用清理方法
    if (process.platform === 'win32') {
      const appRoot = getAppRoot()
      const pythonExePath = path.join(appRoot, 'environment', 'python', 'python.exe')

      return new Promise(resolve => {
        // 使用更简单的命令强制结束相关进程
        exec(`taskkill /f /im python.exe`, error => {
          if (error) {
            logService.warn('进程管理', `备用清理方法失败: ${error.message}`)
          } else {
            logService.info('进程管理', '备用清理方法执行成功')
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
    logService.error('配置管理', '加载配置失败')
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
    logService.error('配置管理', '保存配置失败')
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
          logService.info('托盘管理', `成功加载托盘图标: ${iconPath}`)
          break
        }
      }
    }

    // 如果所有路径都失败，创建一个默认图标
    if (!trayIcon || trayIcon.isEmpty()) {
      logService.warn('托盘管理', '无法加载托盘图标，使用默认图标')
      trayIcon = nativeImage.createEmpty()
    }
  } catch (error) {
    logService.error('托盘管理', '加载托盘图标失败')
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
    logService.warn('托盘管理', '防幽灵机制：强制显示托盘图标')
  }

  if (shouldShowTray && !tray) {
    createTray()
    logService.info('托盘管理', '托盘图标已创建')
  } else if (!shouldShowTray && tray) {
    destroyTray()
    logService.info('托盘管理', '托盘图标已销毁')
  }
}

let mainWindow: Electron.BrowserWindow | null = null

function createWindow() {
  logService.info('窗口管理', '开始创建主窗口')

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
      logService.info('窗口管理', '页面加载完成，窗口已显示')
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
    logService.info('窗口管理', `加载开发服务器: ${devServer}`)
    win.loadURL(devServer)
  } else {
    const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
    logService.info('窗口管理', `加载生产环境页面: ${indexHtmlPath}`)
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
      logService.info('窗口管理', '窗口已最小化到托盘，任务栏图标已隐藏')
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
          logService.info('窗口管理', '窗口状态已保存')
        } catch (error) {
          logService.error('窗口管理', '保存窗口状态失败')
        }
      }
    }
  })

  win.on('closed', () => {
    logService.info('窗口管理', '主窗口已关闭')
    // 清理监听（可选）
    screen.removeListener('display-metrics-changed', recomputeMinSize)
    // 置空模块级引用
    mainWindow = null

    // 如果是正在退出，立即执行进程清理
    if (isQuitting) {
      logService.info('窗口管理', '窗口关闭，执行最终清理')
      setTimeout(async () => {
        try {
          await forceKillRelatedProcesses()
        } catch (e) {
          logService.error('窗口管理', '最终清理失败')
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
      logService.info('窗口管理', '窗口已最小化到托盘，任务栏图标已隐藏')
    }
  })

  win.on('show', () => {
    const currentConfig = loadConfig()
    win.setSkipTaskbar(false)
    updateTrayVisibility(currentConfig)
    logService.info('窗口管理', '窗口已显示，任务栏图标已恢复')
  })

  win.on('hide', () => {
    const currentConfig = loadConfig()
    if (currentConfig.UI.IfToTray) {
      win.setSkipTaskbar(true)
      logService.info('窗口管理', '窗口已隐藏，任务栏图标已隐藏')
    }
    updateTrayVisibility(currentConfig)
  })

  // 移动/调整大小/最大化状态变化时保存
  win.on('moved', saveWindowState)
  win.on('resized', saveWindowState)
  win.on('maximize', saveWindowState)
  win.on('unmaximize', saveWindowState)

  // 主窗口创建完成
  logService.info('窗口管理', '主窗口创建完成')

  // 注册初始化处理器
  registerInitializationHandlers(win)
  logService.info('应用初始化', '初始化处理器已注册')

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
        logService.info('应用启动', '应用初次启动后直接最小化到托盘')
      } else {
        win.minimize()
        logService.info('应用启动', '应用初次启动后直接最小化')
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
        logService.warn('窗口管理', '窗口已销毁，跳过保存状态')
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
      logService.info('窗口管理', '窗口状态已保存')
    } catch (error) {
      logService.error('窗口管理', '保存窗口状态失败')
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
  logService.info('应用控制', '重启应用程序...')
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
    logService.error('进程管理', '获取进程信息失败')
    return []
  }
})

ipcMain.handle('kill-all-processes', async () => {
  try {
    await forceKillRelatedProcesses()
    return { success: true }
  } catch (error) {
    logService.error('进程管理', '强制清理进程失败')
    return { success: false, error: error instanceof Error ? error.message : String(error) }
  }
})

// 添加一个测试用的强制退出命令
ipcMain.handle('force-exit', async () => {
  logService.info('应用控制', '收到强制退出命令')
  isQuitting = true

  // 立即清理进程
  try {
    await forceKillRelatedProcesses()
  } catch (e) {
    logService.error('进程管理', '强制清理失败')
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
      logService.error('文件系统', `打开链接失败: ${error.message}`)
      return { success: false, error: error.message }
    } else {
      logService.error('文件系统', `未知错误: ${error}`)
      return { success: false, error: String(error) }
    }
  }
})

// 打开文件
ipcMain.handle('open-file', async (_event, filePath: string) => {
  try {
    await shell.openPath(filePath)
  } catch (error) {
    logService.error('文件系统', `打开文件失败: ${error}`)
    throw error
  }
})

// 显示文件所在目录并选中文件
ipcMain.handle('show-item-in-folder', async (_event, filePath: string) => {
  try {
    shell.showItemInFolder(filePath)
  } catch (error) {
    logService.error('文件系统', `显示文件所在目录失败: ${error}`)
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

    logService.info('环境检查', '关键文件检查结果')
    return result
  } catch (error) {
    logService.error('环境检查', '检查关键文件失败')
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
        logService.warn('主题管理', '读取主题配置失败，使用默认值')
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
    logService.error('主题管理', '获取主题信息失败')
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
    logService.error('文件系统', `获取路径 ${name} 失败`)
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
        logService.warn('主题管理', '读取主题配置失败，使用默认值')
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
    logService.error('主题管理', '获取对话框主题失败')
    return nativeTheme.shouldUseDarkColors ? 'dark' : 'light'
  }
})

// 全局存储对话框窗口和回调
let dialogWindows = new Map<string, BrowserWindow>()
let dialogCallbacks = new Map<string, (result: boolean) => void>()

// 创建对话框窗口（独立窗口，加载 Vue popup 路由）
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

    // 获取主窗口的位置用于居中显示
    let windowBounds = { width: 800, height: 600, x: 100, y: 100 }
    if (mainWindow && !mainWindow.isDestroyed()) {
      windowBounds = mainWindow.getBounds()
    }

    // 创建对话框窗口
    const dialogWindow = new BrowserWindow({
      width: 500,
      height: 240,
      x: windowBounds.x + (windowBounds.width - 500) / 2,
      y: windowBounds.y + (windowBounds.height - 240) / 2,
      resizable: false,
      minimizable: false,
      maximizable: false,
      alwaysOnTop: true,
      show: false,
      frame: false,
      modal: mainWindow ? true : false,
      parent: mainWindow || undefined,
      transparent: true,
      backgroundColor: '#00000000',
      icon: path.join(__dirname, '../public/AUTO-MAS.ico'),
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        preload: path.join(__dirname, 'preload.js'),
        additionalArguments: ['--is-dialog-window'], // 标记为对话框窗口
      },
    })

    // 存储窗口引用
    dialogWindows.set(messageId, dialogWindow)

    // 编码对话框数据
    const encodedData = encodeURIComponent(JSON.stringify(dialogData))

    // 加载 Vue 应用的 popup 路由
    const devServer = process.env.VITE_DEV_SERVER_URL
    const popupUrl = devServer
      ? `${devServer}#/popup?data=${encodedData}`
      : `file://${path.join(__dirname, '../dist/index.html')}#/popup?data=${encodedData}`

    dialogWindow.loadURL(popupUrl)

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

    logService.info('对话框管理', `对话框窗口已创建: ${messageId}`)
  })
}

// 显示问题对话框
ipcMain.handle('show-question-dialog', async (_event, questionData) => {
  logService.info('对话框管理', '收到显示对话框请求')
  try {
    const result = await createQuestionDialog(questionData)
    logService.info('对话框管理', `对话框结果: ${result}`)
    return result
  } catch (error) {
    logService.error('对话框管理', '创建对话框失败')
    return false
  }
})

// 处理对话框响应
ipcMain.handle('dialog-response', async (_event, messageId: string, choice: boolean) => {
  logService.info('对话框管理', `收到对话框响应`)

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
    logService.info('配置管理', `配置已保存到: ${configPath}`)

    // 如果是UI配置更新，需要更新托盘状态
    if (config.UI) {
      updateTrayVisibility(config)
    }
  } catch (error) {
    logService.error('配置管理', '保存配置文件失败')
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

    logService.info('托盘管理', '托盘设置已更新')
    return true
  } catch (error) {
    logService.error('托盘管理', '更新托盘设置失败')
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

    logService.info('配置管理', '后端配置已同步')
    return true
  } catch (error) {
    logService.error('配置管理', '同步后端配置失败')
    throw error
  }
})

ipcMain.handle('load-config', async () => {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (fs.existsSync(configPath)) {
      const config = fs.readFileSync(configPath, 'utf8')
      logService.info('配置管理', `从文件加载配置: ${configPath}`)
      return JSON.parse(config)
    }

    return null
  } catch (error) {
    logService.error('配置管理', '加载配置文件失败')
    return null
  }
})

ipcMain.handle('reset-config', async () => {
  try {
    const appRoot = getAppRoot()
    const configPath = path.join(appRoot, 'config', 'frontend_config.json')

    if (fs.existsSync(configPath)) {
      fs.unlinkSync(configPath)
      logService.info('配置管理', `配置文件已删除: ${configPath}`)
    }
  } catch (error) {
    logService.error('配置管理', '重置配置文件失败')
    throw error
  }
})

// 日志文件操作
ipcMain.handle('get-log-path', async () => {
  try {
    return logService.getLogPath()
  } catch (error) {
    logService.error('日志管理', '获取日志路径失败')
    throw error
  }
})

ipcMain.handle('get-log-files', async _event => {
  try {
    return logService.getLogFiles()
  } catch (error) {
    logService.error('日志管理', '获取日志文件列表失败')
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
      logFilePath = logService.getLogPath()
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
    logService.error('日志管理', '读取日志文件失败')
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
      logFilePath = logService.getLogPath()
    }

    if (fs.existsSync(logFilePath)) {
      fs.writeFileSync(logFilePath, '', 'utf8')
      logService.info('日志管理', `日志文件已清空: ${fileName || '当前文件'}`)
    }
  } catch (error) {
    logService.error('日志管理', '清空日志文件失败')
    throw error
  }
})

ipcMain.handle('clean-old-logs', async (_event, daysToKeep = 7) => {
  try {
    logService.cleanOldLogs()
    logService.info('日志管理', `已清理${daysToKeep}天前的旧日志文件`)
  } catch (error) {
    logService.error('日志管理', '清理旧日志文件失败')
    throw error
  }
})

// 日志解析相关的IPC处理程序 - 恢复后端日志处理
ipcMain.handle('log:parseBackendLog', async (_event, logLine: string) => {
  try {
    // 动态导入LoguruBackendLogParser
    const { LoguruBackendLogParser } = await import('./utils/loguruBackendLogParser')
    const parser = LoguruBackendLogParser.getInstance()
    const parsedLog = parser.parse(logLine)

    return {
      timestamp: parsedLog.timestamp,
      level: parsedLog.level,
      module: parsedLog.module,
      message: parsedLog.message,
      source: parsedLog.source,
      originalLog: parsedLog.originalLog,
      isValid: parsedLog.isValid
    }
  } catch (error) {
    console.error('后端日志解析失败:', error)
    return { timestamp: new Date(), level: 'ERROR', module: '解析器', message: `解析失败: ${error}` }
  }
})

ipcMain.handle('log:processLogColors', async (_event, logContent: string, enableColorHighlight: boolean) => {
  try {
    // 动态导入ColorProcessor
    const { ColorProcessor } = await import('./utils/colorProcessor')

    if (enableColorHighlight) {
      // 处理HTML颜色标签
      return ColorProcessor.htmlToAnsi(logContent)
    } else {
      // 移除颜色标签
      return ColorProcessor.stripHtmlColors(logContent)
    }
  } catch (error) {
    console.error('后端日志颜色处理失败:', error)
    return logContent // 出错时返回原始内容
  }
})

// 检查是否已经是格式化后的日志
function isAlreadyFormattedLog(logData: string): boolean {
  if (!logData || !logData.trim()) {
    return false
  }

  // 检查是否包含HTML颜色标签（更全面的检测）
  const hasColorTags = /<(\w+?)>.*?<\/\1>/.test(logData)
  if (hasColorTags) {
    return true
  }

  // 检查是否包含嵌套的日志格式（两个时间戳和两个模块名）
  const hasNestedFormat = /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}.*\|\s*\w+.*\|.*\|.*\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}.*\|\s*\w+.*\|/.test(logData)
  if (hasNestedFormat) {
    return true
  }

  // 检查是否包含ANSI颜色代码
  const hasAnsiColors = /\x1b\[[0-9;]*m/.test(logData)
  if (hasAnsiColors) {
    return true
  }

  // 检查是否已经是标准格式的日志（时间戳 | 级别 | 模块 | 消息）
  const hasStandardFormat = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*\w+\s*\|\s*\w+\s*\|/.test(logData)
  if (hasStandardFormat) {
    // 进一步检查是否包含HTML标签，如果包含则认为是已格式化的
    return /<[^>]+>/.test(logData)
  }

  return false
}

// 处理HTML颜色标签，转换为Monaco Editor可显示的HTML
function processHtmlColorTags(logLine: string): string {
  // 将HTML颜色标签转换为Monaco Editor支持的HTML格式
  return logLine.replace(/<(\w+?)>(.*?)<\/\1>/g, (match, color, content) => {
    // 根据颜色标签类型设置样式
    let style = ''

    switch (color.toLowerCase()) {
      case 'level':
        // 对于level标签，需要根据日志级别设置颜色
        const levelMatch = content.trim().match(/^(\w+)/)
        if (levelMatch) {
          const level = levelMatch[1].toUpperCase()
          style = getLevelStyle(level)
        } else {
          // 如果无法提取日志级别，使用默认样式
          style = 'color: #666666; font-weight: bold;'
        }
        break
      case 'green':
        style = 'color: #52c41a; font-weight: bold;'
        break
      case 'cyan':
        style = 'color: #1890ff; font-weight: bold;'
        break
      case 'red':
        style = 'color: #ff4d4f; font-weight: bold;'
        break
      case 'yellow':
        style = 'color: #faad14; font-weight: bold;'
        break
      case 'blue':
        style = 'color: #1890ff; font-weight: bold;'
        break
      case 'magenta':
        style = 'color: #722ed1; font-weight: bold;'
        break
      default:
        style = `color: #666666; font-weight: bold;`
    }

    return `<span style="${style}">${content}</span>`
  })
}

// 为解析后的日志添加颜色
function addColorsToParsedLog(parsedLog: any): string {
  const timestamp = parsedLog.timestamp ? parsedLog.timestamp.toISOString().replace('T', ' ').substring(0, 23) : ''
  const level = parsedLog.level || 'INFO'
  const module = parsedLog.module || '未知模块'
  const message = parsedLog.message || ''

  const levelStyle = getLevelStyle(level)
  const moduleStyle = 'color: #1890ff; background-color: #f0f5ff; padding: 2px 6px; border-radius: 3px;'

  return `${timestamp} | <span style="${levelStyle}">${level}</span> | <span style="${moduleStyle}">${module}</span> | ${message}`
}

// 获取日志级别对应的样式
function getLevelStyle(level: string): string {
  switch (level.toUpperCase()) {
    case 'DEBUG':
      return 'color: #666666; background-color: #f8f8f8; padding: 2px 6px; border-radius: 3px; font-weight: bold;'
    case 'INFO':
      return 'color: #52c41a; background-color: #f6ffed; padding: 2px 6px; border-radius: 3px; font-weight: bold;'
    case 'WARN':
      return 'color: #faad14; background-color: #fffbe6; padding: 2px 6px; border-radius: 3px; font-weight: bold;'
    case 'ERROR':
      return 'color: #ff4d4f; background-color: #fff2f0; padding: 2px 6px; border-radius: 3px; font-weight: bold;'
    default:
      return 'color: #666666; background-color: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-weight: bold;'
  }
}

// 处理ANSI颜色代码，转换为HTML格式
function processAnsiColors(logLine: string): string {
  // 使用ColorProcessor处理ANSI颜色代码
  const { ColorProcessor } = require('./utils/colorProcessor')
  const htmlLine = ColorProcessor.htmlToAnsi(logLine)

  // 如果包含ANSI代码，将其转换为HTML
  if (logLine.includes('\x1b[')) {
    // 简单的ANSI到HTML转换
    return logLine
      .replace(/\x1b\[31m/g, '<span style="color: #ff4d4f;">') // 红色
      .replace(/\x1b\[32m/g, '<span style="color: #52c41a;">') // 绿色
      .replace(/\x1b\[33m/g, '<span style="color: #faad14;">') // 黄色
      .replace(/\x1b\[34m/g, '<span style="color: #1890ff;">') // 蓝色
      .replace(/\x1b\[35m/g, '<span style="color: #722ed1;">') // 紫色
      .replace(/\x1b\[36m/g, '<span style="color: #13c2c2;">') // 青色
      .replace(/\x1b\[37m/g, '<span style="color: #ffffff;">') // 白色
      .replace(/\x1b\[90m/g, '<span style="color: #666666;">') // 亮黑(灰色)
      .replace(/\x1b\[91m/g, '<span style="color: #ff7875;">') // 亮红
      .replace(/\x1b\[92m/g, '<span style="color: #95de64;">') // 亮绿
      .replace(/\x1b\[93m/g, '<span style="color: #fff566;">') // 亮黄
      .replace(/\x1b\[94m/g, '<span style="color: #69c0ff;">') // 亮蓝
      .replace(/\x1b\[95m/g, '<span style="color: #b37feb;">') // 亮紫
      .replace(/\x1b\[96m/g, '<span style="color: #5cdbd3;">') // 亮青
      .replace(/\x1b\[97m/g, '<span style="color: #ffffff;">') // 亮白
      .replace(/\x1b\[0m/g, '</span>') // 重置
      .replace(/\x1b\[1m/g, '<span style="font-weight: bold;">') // 粗体
      .replace(/\x1b\[22m/g, '</span>') // 取消粗体
  }

  return htmlLine
}

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
    logService.info('日志管理', `日志已保存到: ${logFilePath}`)
  } catch (error) {
    logService.error('日志管理', '保存日志文件失败')
    throw error
  }
})

ipcMain.handle('load-logs-from-file', async () => {
  try {
    const appRoot = getAppRoot()
    const logFilePath = path.join(appRoot, 'logs', 'app.log')

    if (fs.existsSync(logFilePath)) {
      const logs = fs.readFileSync(logFilePath, 'utf8')
      logService.info('日志管理', `从文件加载日志: ${logFilePath}`)
      return logs
    }

    return null
  } catch (error) {
    logService.error('日志管理', '加载日志文件失败')
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

// 在沙箱环境下运行会导致无法启动子进程，强制禁用沙箱
app.commandLine.appendSwitch('no-sandbox')

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

    logService.info('应用生命周期', '应用准备退出')

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
      logService.info('应用生命周期', '初始化资源清理完成')
    } catch (e) {
      logService.error('应用生命周期', '资源清理失败')
    }

    // 立即开始强制清理，不等待优雅关闭
    logService.info('应用生命周期', '开始强制清理所有相关进程')

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

      logService.info('应用生命周期', '进程清理完成')
    } catch (e) {
      logService.error('应用生命周期', '进程清理时出错')
    }

    logService.info('应用生命周期', '应用强制退出')

    // 使用 process.exit 而不是 app.exit，更加强制
    setTimeout(() => {
      process.exit(0)
    }, 500)
  }
})

app.whenReady().then(async () => {
  // 初始化日志系统
  logService.initialize()

  // 初始化日志管理服务
  try {
    await logManagementService.initialize()

    // 设置日志管理服务的事件监听
    logManagementService.on('log-added', (log) => {
      // 可以在这里处理新添加的日志
    })

    logManagementService.on('error', (error) => {
      logService.error('日志管理服务', `错误: ${error}`)
    })

    logService.info('日志管理服务', '日志管理服务初始化完成')
  } catch (error) {
    logService.error('日志管理服务', `初始化失败: ${error}`)
  }

  // 清理7天前的旧日志
  logService.cleanOldLogs()

  logService.info('应用启动', `应用版本: ${app.getVersion()}`)
  logService.info('应用启动', `Electron版本: ${process.versions.electron}`)
  logService.info('应用启动', `Node版本: ${process.versions.node}`)
  logService.info('应用启动', `平台: ${process.platform}`)

  // 检查管理员权限
  if (!isRunningAsAdmin()) {
    logService.warn('应用启动', '应用未以管理员权限运行')
    // 在生产环境中，可以选择是否强制要求管理员权限
    // 这里先创建窗口，让用户选择是否重新启动
  } else {
    logService.info('应用启动', '应用以管理员权限运行')
  }

  createWindow()
})

app.on('window-all-closed', async () => {
  if (process.platform !== 'darwin') {
    isQuitting = true

    // 销毁日志管理服务
    try {
      await logManagementService.destroy()
      logService.info('应用退出', '日志管理服务已销毁')
    } catch (error) {
      logService.error('应用退出', `销毁日志管理服务失败: ${error}`)
    }

    app.quit()
  }
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})

// 日志管理服务IPC处理器
ipcMain.handle('logManagement:initialize', async (_, config) => {
  try {
    // logManagementService.initialize() is already called above
    return { success: true }
  } catch (error) {
    logService.error('日志管理服务', `初始化失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:processLog', async (_, rawLog, source) => {
  try {
    const result = await logManagementService.processLog(rawLog, source)
    return result
  } catch (error) {
    logService.error('日志管理服务', `处理日志失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:processBatchLogs', async (_, rawLogs, source) => {
  try {
    const result = await logManagementService.processBatchLogs(rawLogs, source)
    return result
  } catch (error) {
    logService.error('日志管理服务', `批量处理日志失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:subscribe', async (_, id, filter) => {
  try {
    const callback = (logs: any[]) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('log-update', logs)
      }
    }

    logManagementService.subscribe(id, callback, filter)
    return { success: true }
  } catch (error) {
    logService.error('日志管理服务', `订阅失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:unsubscribe', async (_, id) => {
  try {
    logManagementService.unsubscribe(id)
    return { success: true }
  } catch (error) {
    logService.error('日志管理服务', `取消订阅失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:toggleSubscriber', async (_, id, enabled) => {
  try {
    logManagementService.toggleSubscriber(id, enabled)
    return { success: true }
  } catch (error) {
    logService.error('日志管理服务', `切换订阅者状态失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:getLogs', async (_, conditions, limit, offset) => {
  try {
    const logs = logManagementService.getLogs(conditions, limit, offset)
    return { success: true, data: logs }
  } catch (error) {
    logService.error('日志管理服务', `获取日志失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:exportLogs', async (_, conditions, format) => {
  try {
    const exportedData = await logManagementService.exportLogs(conditions, format)
    return { success: true, data: exportedData }
  } catch (error) {
    logService.error('日志管理服务', `导出日志失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:clearLogs', async () => {
  try {
    logManagementService.clearLogs()
    return { success: true }
  } catch (error) {
    logService.error('日志管理服务', `清空日志失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:getStats', async () => {
  try {
    const stats = logManagementService.getStats()
    return { success: true, data: stats }
  } catch (error) {
    logService.error('日志管理服务', `获取统计信息失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:resetStats', async () => {
  try {
    logManagementService.resetStats()
    return { success: true }
  } catch (error) {
    logService.error('日志管理服务', `重置统计信息失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:getConfig', async () => {
  try {
    const config = logManagementService.getConfig()
    return { success: true, data: config }
  } catch (error) {
    logService.error('日志管理服务', `获取配置失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:updateConfig', async (_, config) => {
  try {
    logManagementService.updateConfig(config)
    return { success: true }
  } catch (error) {
    logService.error('日志管理服务', `更新配置失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logManagement:getSubscribers', async () => {
  try {
    const subscribers = logManagementService.getSubscribers()
    return { success: true, data: subscribers }
  } catch (error) {
    logService.error('日志管理服务', `获取订阅者失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

// 日志管道IPC处理器
ipcMain.handle('logPipeline:getConfig', async () => {
  try {
    const config = logManagementService.getConfig()
    return { success: true, data: config.pipelineConfig }
  } catch (error) {
    logService.error('日志管道', `获取配置失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logPipeline:updateConfig', async (_, config) => {
  try {
    logManagementService.updateConfig({ pipelineConfig: config })
    return { success: true }
  } catch (error) {
    logService.error('日志管道', `更新配置失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logPipeline:getParserStats', async () => {
  try {
    const stats = logManagementService.getStats()
    return { success: true, data: stats.parserStats }
  } catch (error) {
    logService.error('日志管道', `获取解析器统计失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logPipeline:toggleParser', async (_, parserName, enabled) => {
  try {
    // 这里需要实现解析器切换逻辑
    return { success: true }
  } catch (error) {
    logService.error('日志管道', `切换解析器失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logPipeline:clearCache', async () => {
  try {
    // 这里需要实现缓存清理逻辑
    return { success: true }
  } catch (error) {
    logService.error('日志管道', `清理缓存失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logPipeline:getCacheStats', async () => {
  try {
    const stats = logManagementService.getStats()
    return { success: true, data: stats.cacheStats }
  } catch (error) {
    logService.error('日志管道', `获取缓存统计失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logPipeline:flush', async () => {
  try {
    // 这里需要实现刷新逻辑
    return { success: true }
  } catch (error) {
    logService.error('日志管道', `刷新失败: ${error}`)
    return { success: false, error: String(error) }
  }
})

ipcMain.handle('logPipeline:getBatchStats', async () => {
  try {
    const stats = logManagementService.getStats()
    return { success: true, data: stats.batchStats }
  } catch (error) {
    logService.error('日志管道', `获取批处理统计失败: ${error}`)
    return { success: false, error: String(error) }
  }
})
