const fs = require('node:fs')
const path = require('node:path')
const { spawn } = require('node:child_process')
const DEV_SERVER_URL = 'http://127.0.0.1:5173/'

if (process.versions.electron && process.type === 'browser') {
  let electron
  let stopping = false
  let relaunchPending = false
  let quitEvent
  let releasePage
  const pageReady = new Promise(resolve => {
    releasePage = resolve
  })
  // 开发启动器退出时也走应用原有的 Runtime 协调退出。
  const quit = () => {
    stopping = true
    relaunchPending = false
    releasePage()
    electron?.app.quit()
  }
  process.on('message', message => {
    if (message === 'auto-mas-dev-quit') quit()
    if (message === 'auto-mas-dev-vite-ready') releasePage()
    if (message === 'auto-mas-dev-relaunch-accepted' && relaunchPending) {
      relaunchPending = false
      electron?.app.quit()
    }
  })
  process.on('disconnect', quit)
  // 预加载早于 Electron 内置模块可用，等应用首次正常导入后再接入。
  const Module = require('node:module')
  const load = Module._load
  Module._load = function (request, ...args) {
    const result = load.call(this, request, ...args)
    if (request === 'electron' && result.app && !electron) {
      electron = result
      electron.app.on('before-quit', event => {
        if (relaunchPending) event.preventDefault()
      })
      electron.app.on('will-quit', event => {
        quitEvent = event
      })
      electron.app.relaunch = options => {
        if (stopping) return
        relaunchPending = true
        // 定时唤醒也在 will-quit 提交重启，须等启动器接收后再退出。
        quitEvent?.preventDefault()
        process.send({ type: 'auto-mas-dev-relaunch', options }, error => {
          if (error) quit()
        })
      }
      const loadURL = electron.BrowserWindow.prototype.loadURL
      electron.BrowserWindow.prototype.loadURL = function (url, ...options) {
        if (!url.startsWith(DEV_SERVER_URL)) return loadURL.call(this, url, ...options)
        const loading = pageReady.then(() => {
          if (stopping)
            throw Object.assign(new Error('开发页面加载已取消'), { code: 'ERR_ABORTED' })
          return loadURL.call(this, url, ...options)
        })
        void loading.catch(() => {})
        return loading
      }
      if (stopping) electron.app.quit()
    }
    return result
  }
  process.send?.('auto-mas-dev-connect')
} else if (process.connected && path.basename(process.argv[1] ?? '') === 'tsc') {
  // 启动器被直接终止时，watch 也随 IPC 断连退出。
  process.once('disconnect', () => process.exit())
} else if (require.main === module) {
  const root = path.resolve(__dirname, '..')
  process.chdir(root)
  let server
  let watcher
  let desktop
  let typechecker
  let closing = false
  let resourcesClosed = false
  let serverStart

  async function close(code = 0) {
    process.exitCode = Math.max(process.exitCode ?? 0, code)
    closing = true
    typechecker?.kill()
    if (desktop && desktop.exitCode === null && desktop.signalCode === null) {
      if (desktop.connected) desktop.send('auto-mas-dev-quit')
      return
    }
    if (resourcesClosed) return
    resourcesClosed = true
    await serverStart?.catch(() => {})
    await Promise.allSettled([server?.close(), watcher?.close()])
  }

  process.on('SIGINT', () => void close())
  process.on('SIGTERM', () => void close())

  async function main() {
    // 先拒绝已占用端口；页面仍只在本次 Vite 真正监听成功后放行。
    await new Promise((resolve, reject) => {
      const probe = require('node:net').createServer()
      probe.once('error', reject)
      probe.listen(5173, '127.0.0.1', () => probe.close(resolve))
    })
    const { watch } = await import('vite/rolldown')
    if (closing) return
    const mainEntry = path.resolve('electron/main.ts')
    const started = performance.now()
    watcher = watch({
      input: mainEntry,
      plugins: [
        {
          name: 'electron-entrypoints',
          buildStart() {
            // 独立 preload 没有 import 边，目录变化也必须触发入口重新发现。
            this.addWatchFile(path.resolve('electron'))
            for (const entry of fs.readdirSync('electron', {
              recursive: true,
              withFileTypes: true,
            })) {
              const filename = path.resolve(entry.parentPath, entry.name)
              if (entry.isDirectory()) this.addWatchFile(filename)
              else if (
                filename !== mainEntry &&
                entry.name.endsWith('.ts') &&
                !entry.name.endsWith('.test.ts') &&
                !entry.name.endsWith('.d.ts')
              ) {
                this.emitFile({ type: 'chunk', id: filename })
              }
            }
          },
        },
      ],
      external: id => !id.startsWith('.') && !path.isAbsolute(id),
      platform: 'node',
      treeshake: false,
      preserveEntrySignatures: 'strict',
      output: {
        dir: 'dist-electron',
        format: 'cjs',
        exports: 'named',
        preserveModules: true,
        preserveModulesRoot: 'electron',
        entryFileNames: '[name].js',
      },
    })
    const compiled = new Promise((resolve, reject) => {
      watcher.on('event', event => {
        if (event.code === 'BUNDLE_END') {
          console.log(`[dev] Electron compiled in ${event.duration} ms`)
          void event.result.close().then(resolve, reject)
        } else if (event.code === 'ERROR') {
          console.error(event.error)
          reject(event.error)
        }
      })
    })
    await compiled
    if (closing) return
    console.log(`[dev] Electron launch ready in ${(performance.now() - started).toFixed(0)} ms`)
    const releasePage = () => {
      if (server?.resolvedUrls?.local.includes(DEV_SERVER_URL) && desktop?.connected)
        desktop.send('auto-mas-dev-vite-ready')
    }
    function launchDesktop(options) {
      const child = spawn(
        options?.execPath ?? require('electron'),
        options?.args ?? ['.', ...process.argv.slice(2)],
        {
          cwd: root,
          windowsHide: true,
          stdio: ['inherit', 'inherit', 'inherit', 'ipc'],
          env: {
            ...process.env,
            VITE_DEV_SERVER_URL: DEV_SERVER_URL,
            NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ''} --require "${__filename.replaceAll('\\', '/')}"`,
          },
        }
      )
      desktop = child
      let relaunchRequested = false
      let relaunchOptions
      child.once('close', (code, signal) => {
        if (desktop !== child) return
        desktop = undefined
        if (relaunchRequested && !closing && code === 0 && !signal) launchDesktop(relaunchOptions)
        else void close(code ?? 1)
      })
      child.once('error', error => {
        if (desktop !== child) return
        console.error(error)
        desktop = undefined
        void close(1)
      })
      child.on('message', message => {
        if (desktop !== child) return
        if (message === 'auto-mas-dev-connect') releasePage()
        if (message?.type === 'auto-mas-dev-relaunch' && !closing) {
          relaunchRequested = true
          relaunchOptions = message.options
          child.send('auto-mas-dev-relaunch-accepted')
        }
      })
    }
    launchDesktop()
    serverStart = import('vite')
      .then(({ createServer }) =>
        createServer({
          server: { warmup: { clientFiles: ['./src/main.ts', './src/views/Home.vue'] } },
        })
      )
      .then(async vite => {
        server = vite
        await vite.listen()
        if (!vite.resolvedUrls.local.includes(DEV_SERVER_URL))
          throw new Error('Vite 开发地址与入口不一致')
        vite.printUrls()
        releasePage()
      })
    await serverStart
    if (closing) return
    // 类型检查不阻塞启动，也不与 Rolldown 争写 dist-electron。
    typechecker = spawn(
      process.execPath,
      [
        '--require',
        __filename,
        require.resolve('typescript/bin/tsc'),
        '-p',
        'tsconfig.electron.json',
        '--noEmit',
        '--watch',
        '--preserveWatchOutput',
      ],
      { cwd: root, windowsHide: true, stdio: ['inherit', 'inherit', 'inherit', 'ipc'] }
    )
    typechecker.once('error', error => {
      console.error(error)
      void close(1)
    })
    typechecker.once('exit', (code, signal) => {
      if (!closing) {
        console.error(`[dev] Electron 类型检查意外退出 (${code ?? signal})`)
        void close(1)
      }
    })
  }

  void main().catch(error => {
    console.error(error)
    void close(1)
  })
}
