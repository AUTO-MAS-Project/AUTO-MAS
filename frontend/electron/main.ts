import { app, BrowserWindow, ipcMain } from 'electron'
import * as path from 'path'

let mainWindow: BrowserWindow | null = null

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        minWidth: 800,
        minHeight: 600,
        icon: path.join(__dirname, '../public/AUTO_MAA.ico'), // 设置应用图标
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true
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
        mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
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

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
    if (mainWindow === null) createWindow()
})
