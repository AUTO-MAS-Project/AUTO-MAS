const electron = require('electron')
const fs = require('node:fs')
const path = require('node:path')

const frontendRoot = path.resolve(__dirname, '../..')
const runRoot = process.env.AUTO_MAS_E2E_DATA_ROOT
const root = process.env.AUTO_MAS_WINDOW_E2E_ROOT
if (!runRoot || !root || path.dirname(root) !== runRoot) {
  throw new Error('请通过 yarn e2e --grep @window 启动隔离窗口验证')
}

try {
  // 真正主入口根据 appPath 的父目录读写配置；Chromium 缓存也留在同一次临时运行内。
  const appPath = path.join(root, 'frontend')
  fs.mkdirSync(appPath, { recursive: true })
  fs.writeFileSync(
    path.join(appPath, 'package.json'),
    JSON.stringify({
      name: path.basename(root),
      version: require(path.join(frontendRoot, 'package.json')).version,
    })
  )
  const appData = path.join(root, 'user-data')
  fs.mkdirSync(appData, { recursive: true })
  electron.app.setAppPath(appPath)
  electron.app.setName(path.basename(root))
  electron.app.setPath('appData', appData)

  const events = []
  const trays = []
  let mainWindow
  let failTrayIcon = false
  const snapshot = () => ({
    appPath: electron.app.getAppPath(),
    userData: electron.app.getPath('userData'),
    visible: mainWindow ? mainWindow.isVisible() : false,
    minimized: mainWindow ? mainWindow.isMinimized() : false,
    maximized: mainWindow ? mainWindow.isMaximized() : false,
    trayCount: trays.filter(tray => !tray.isDestroyed()).length,
    events: [...events],
  })
  const record = name => {
    events.push({
      name,
      visible: mainWindow ? mainWindow.isVisible() : false,
      minimized: mainWindow ? mainWindow.isMinimized() : false,
      trayCount: trays.filter(tray => !tray.isDestroyed()).length,
    })
  }

  electron.app.on('browser-window-created', (_event, window) => {
    if (mainWindow) return
    mainWindow = window
    record('created')
    for (const name of ['show', 'hide', 'minimize', 'restore', 'maximize']) {
      window.on(name, () => record(name))
    }
    window.webContents.on('did-finish-load', () => record('loaded'))
  })

  // 观察真实 Tray 的公开方法，不替换 BrowserWindow 或主进程。
  const setToolTip = electron.Tray.prototype.setToolTip
  electron.Tray.prototype.setToolTip = function (text) {
    setToolTip.call(this, text)
    if (!trays.includes(this)) {
      trays.push(this)
      record('tray-created')
    }
  }
  // 损坏或无法解码的托盘图标是可达的外部失败，窗口必须保留恢复入口。
  const createFromPath = electron.nativeImage.createFromPath
  electron.nativeImage.createFromPath = filePath => {
    if (failTrayIcon) {
      record('tray-failed')
      return electron.nativeImage.createEmpty()
    }
    return createFromPath(filePath)
  }

  globalThis.windowBehaviorE2E = {
    snapshot,
    failTrayIcon: value => {
      failTrayIcon = value
    },
    dispose: async () => {
      const { stopDesktopStartup } = require(
        path.join(frontendRoot, 'dist-electron/ipc/initializationHandlers.js')
      )
      await stopDesktopStartup(true)
      // 结束验证时跳过关闭确认，will-quit 仍释放快捷键、桌宠和统计资源。
      electron.app.removeAllListeners('before-quit')
      mainWindow?.removeAllListeners('close')
    },
  }

  require(path.join(frontendRoot, 'dist-electron/main.js'))
} catch (error) {
  fs.writeFileSync(path.join(root, 'fixture-startup-error.txt'), String(error.stack))
  console.error(error)
  electron.app.exit(1)
}
