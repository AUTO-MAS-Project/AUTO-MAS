import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import * as path from 'path'
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

// 应用生命周期
app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})