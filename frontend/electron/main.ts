import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import * as path from 'path'
import * as fs from 'fs'
import { getAppRoot, checkEnvironment } from './services/environmentService'
import { setMainWindow as setDownloadMainWindow } from './services/downloadService'
import { setMainWindow as setPythonMainWindow, downloadPython, installDependencies, startBackend } from './services/pythonService'
import { setMainWindow as setGitMainWindow, downloadGit, cloneBackend } from './services/gitService'

let mainWindow: BrowserWindow | null = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 900,
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
  if (!mainWindow) return null
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    title: '选择文件',
    filters: filters.length > 0 ? filters : [{ name: '所有文件', extensions: ['*'] }],
  })
  return result.canceled ? null : result.filePaths[0]
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

ipcMain.handle('clone-backend', async (event, repoUrl = 'https://github.com/DLmaster361/AUTO_MAA.git') => {
  const appRoot = getAppRoot()
  return cloneBackend(appRoot, repoUrl)
})

ipcMain.handle('update-backend', async (event, repoUrl = 'https://github.com/DLmaster361/AUTO_MAA.git') => {
  const appRoot = getAppRoot()
  return cloneBackend(appRoot, repoUrl) // 使用相同的逻辑，会自动判断是pull还是clone
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

// 应用生命周期
app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})