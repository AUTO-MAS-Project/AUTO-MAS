import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron'
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

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 800,
    minHeight: 600,
    icon: path.join(__dirname, '../src/assets/AUTO_MAA.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    autoHideMenuBar: true,
  })

  mainWindow.setMenuBarVisibility(false)
  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    mainWindow.loadURL(devServer)
  } else {
    const indexHtmlPath = path.join(app.getAppPath(), 'dist', 'index.html')
    mainWindow.loadFile(indexHtmlPath)
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // 设置各个服务的主窗口引用
  if (mainWindow) {
    setDownloadMainWindow(mainWindow)
    setPythonMainWindow(mainWindow)
    setGitMainWindow(mainWindow)
  }
}

// IPC处理函数
ipcMain.handle('open-dev-tools', () => {
  if (mainWindow) {
    mainWindow.webContents.openDevTools({ mode: 'undocked' })
  }
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
ipcMain.handle('open-url', async (event, url: string) => {
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

// 环境检查
ipcMain.handle('check-environment', async () => {
  const appRoot = getAppRoot()
  return checkEnvironment(appRoot)
})

// Python相关
ipcMain.handle('download-python', async (event, mirror = 'tsinghua') => {
  const appRoot = getAppRoot()
  return downloadPython(appRoot, mirror)
})

ipcMain.handle('install-pip', async () => {
  const appRoot = getAppRoot()
  return installPipPackage(appRoot)
})

ipcMain.handle('install-dependencies', async (event, mirror = 'tsinghua') => {
  const appRoot = getAppRoot()
  return installDependencies(appRoot, mirror)
})

ipcMain.handle('start-backend', async () => {
  const appRoot = getAppRoot()
  return startBackend(appRoot)
})

// Git相关
ipcMain.handle('download-git', async () => {
  const appRoot = getAppRoot()
  return downloadGit(appRoot)
})

ipcMain.handle(
  'clone-backend',
  async (event, repoUrl = 'https://github.com/DLmaster361/AUTO_MAA.git') => {
    const appRoot = getAppRoot()
    return cloneBackend(appRoot, repoUrl)
  }
)

ipcMain.handle(
  'update-backend',
  async (event, repoUrl = 'https://github.com/DLmaster361/AUTO_MAA.git') => {
    const appRoot = getAppRoot()
    return cloneBackend(appRoot, repoUrl) // 使用相同的逻辑，会自动判断是pull还是clone
  }
)

// 配置文件操作
ipcMain.handle('save-config', async (event, config) => {
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
  } catch (error) {
    console.error('保存配置文件失败:', error)
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
ipcMain.handle('save-logs-to-file', async (event, logs: string) => {
  try {
    const appRoot = getAppRoot()
    const logsDir = path.join(appRoot, 'logs')

    // 确保logs目录存在
    if (!fs.existsSync(logsDir)) {
      fs.mkdirSync(logsDir, { recursive: true })
    }

    const logFilePath = path.join(logsDir, 'app.log')
    fs.writeFileSync(logFilePath, logs, 'utf8')
    console.log(`日志已保存到: ${logFilePath}`)
  } catch (error) {
    console.error('保存日志文件失败:', error)
    throw error
  }
})

ipcMain.handle('load-logs-from-file', async () => {
  try {
    const appRoot = getAppRoot()
    const logFilePath = path.join(appRoot, 'logs', 'app.log')

    if (fs.existsSync(logFilePath)) {
      const logs = fs.readFileSync(logFilePath, 'utf8')
      console.log(`从文件加载日志: ${logFilePath}`)
      return logs
    }

    return null
  } catch (error) {
    console.error('加载日志文件失败:', error)
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
  event.preventDefault()
  try {
    await stopBackend()
  } catch (e) {
    console.error('停止后端时出错:', e)
  } finally {
    app.exit(0)
  }
})

app.whenReady().then(() => {
  // 检查管理员权限
  if (!isRunningAsAdmin()) {
    console.log('应用未以管理员权限运行')
    // 在生产环境中，可以选择是否强制要求管理员权限
    // 这里先创建窗口，让用户选择是否重新启动
  }
  createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})
