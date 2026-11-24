const { app, BrowserWindow, ipcMain, nativeImage, screen } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

const frontendRoot = path.resolve(__dirname, '../..')
const dataRoot = process.env.AUTO_MAS_E2E_DATA_ROOT
if (!dataRoot || process.env.AUTO_MAS_E2E !== '1') throw new Error('请通过 yarn e2e 启动桌宠验证')
app.setAppPath(frontendRoot)
app.setPath('userData', path.join(dataRoot, 'mascot-electron'))
app.on('window-all-closed', () => {})
const AdmZip = require(path.join(frontendRoot, 'node_modules/adm-zip'))
const { importMascotPackage, getMascot } = require(
  path.join(frontendRoot, 'dist-electron/services/mascotPackageService.js')
)
const { DesktopMascotService } = require(
  path.join(frontendRoot, 'dist-electron/services/desktopMascotService.js')
)
const { registerDesktopMascotHandlers } = require(
  path.join(frontendRoot, 'dist-electron/ipc/mascotHandlers.js')
)

// 小型透明图集由测试生成，不依赖作者的资源包、配置或账号。
function atlas(columns, rows, colors) {
  const width = columns * 32
  const height = rows * 32
  const pixels = Buffer.alloc(width * height * 4)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (Math.hypot((x % 32) - 16, (y % 32) - 16) > 12) continue
      const offset = (y * width + x) * 4
      const color = colors[Math.floor(y / 32) % colors.length]
      pixels[offset] = color[2]
      pixels[offset + 1] = color[1]
      pixels[offset + 2] = color[0]
      pixels[offset + 3] = 255
    }
  }
  return nativeImage.createFromBitmap(pixels, { width, height }).toPNG()
}

app
  .whenReady()
  .then(() => {
    fs.mkdirSync(app.getPath('userData'), { recursive: true })
    const images = {
      'assets/pet.png': atlas(1, 1, [[36, 160, 100]]),
      'assets/animation.png': atlas(4, 2, [
        [36, 160, 100],
        [40, 100, 210],
      ]),
      'assets/results.png': atlas(4, 2, [
        [220, 60, 60],
        [40, 180, 100],
      ]),
      'assets/drag.png': atlas(4, 1, [[220, 150, 40]]),
      'assets/look.png': atlas(3, 3, [[70, 150, 160]]),
    }
    const imports = []
    for (const kind of ['full', 'bare', 'static']) {
      const animation =
        kind === 'static'
          ? undefined
          : {
              path: 'assets/animation.png',
              columns: 4,
              idleFps: 4,
              workingFps: 4,
              ...(kind === 'full'
                ? {
                    lookPath: 'assets/look.png',
                    resultPath: 'assets/results.png',
                    dragPath: 'assets/drag.png',
                  }
                : {}),
            }
      const manifest = {
        formatVersion: 1,
        id: `e2e-${kind}`,
        name: `E2E ${kind}`,
        mascot: { path: 'assets/pet.png', width: 96, ...(animation ? { animation } : {}) },
      }
      const archive = new AdmZip()
      archive.addFile('mascot.json', Buffer.from(JSON.stringify(manifest)))
      archive.addFile('assets/pet.png', images['assets/pet.png'])
      for (const asset of animation
        ? Object.values(animation).filter(value => typeof value === 'string')
        : [])
        archive.addFile(asset, images[asset])
      const archivePath = path.join(app.getPath('userData'), `${kind}.zip`)
      archive.writeZip(archivePath)
      imports.push(importMascotPackage(app.getPath('userData'), archivePath))
    }
    if (imports.some(result => !result.success)) throw new Error(JSON.stringify(imports))
    let kind = 'full'
    let preferences = { desktopMascotPosition: { x: 100, y: 350 } }
    let delay = 0
    const positions = []
    const errors = []
    const service = new DesktopMascotService({
      readPreferences: () => preferences,
      resolveAssets: () => getMascot(app.getPath('userData'), `e2e-${kind}`),
      savePosition: position => positions.push(position),
      getInitialBounds: () => undefined,
      onContextMenu: () => {},
      onClosed: () => {},
      onError: error => errors.push(String(error)),
    })
    const disposeHandlers = registerDesktopMascotHandlers(
      service,
      () => null,
      () => {},
      () => {}
    )
    ipcMain.removeHandler('desktop-mascot:drag-start')
    ipcMain.handle('desktop-mascot:drag-start', async (event, offset) => {
      if (delay) await new Promise(resolve => setTimeout(resolve, delay))
      return service.startDrag(event.sender, offset)
    })
    globalThis.mascotE2E = {
      service,
      imports,
      positions,
      errors,
      snapshot: () => service.getData(BrowserWindow.getAllWindows()[0].webContents),
      // Playwright 的合成输入不移动系统光标；仅在此夹具将原生读数对齐到合成位置。
      cursor: position => {
        const bounds = BrowserWindow.getAllWindows()[0].getBounds()
        screen.getCursorScreenPoint = () => ({
          x: Math.round(bounds.x + position.x),
          y: Math.round(bounds.y + position.y),
        })
      },
      delayDrag: value => {
        delay = value
      },
      select: value => {
        kind = value
        service.sync()
      },
      preferences: patch => {
        preferences = { ...preferences, ...patch }
        service.syncPreferences()
      },
      dispose: () => {
        disposeHandlers()
        service.dispose()
      },
    }
    service.setReady(true, { background: '#ffffff', text: '#141414', border: '#d9d9d9', radius: 8 })
  })
  .catch(error => {
    console.error(error)
    app.exit(1)
  })
