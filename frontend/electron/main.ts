import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import * as path from 'path'

let mainWindow: BrowserWindow | null = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 900,
    minWidth: 800,
    minHeight: 600,
    icon: path.join(__dirname, '../src/assets/AUTO_MAA.ico'), // 设置应用图标
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    // 隐藏菜单栏
    autoHideMenuBar: true,
    // 或者完全移除菜单栏（推荐）
    // menuBarVisible: false
  })

  // 完全移除菜单栏
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
}

// 处理开发者工具请求
ipcMain.handle('open-dev-tools', () => {
  if (mainWindow) {
    // 在新窗口中打开开发者工具
    mainWindow.webContents.openDevTools({ mode: 'undocked' })
  }
})

// 处理文件夹选择请求
ipcMain.handle('select-folder', async () => {
  if (!mainWindow) return null

  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: '选择文件夹',
  })

  if (result.canceled) {
    return null
  }

  return result.filePaths[0]
})

// 处理文件选择请求
ipcMain.handle('select-file', async (event, filters = []) => {
  if (!mainWindow) return null

  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    title: '选择文件',
    filters: filters.length > 0 ? filters : [{ name: '所有文件', extensions: ['*'] }],
  })

  if (result.canceled) {
    return null
  }

  return result.filePaths[0]
})

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})
