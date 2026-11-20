const fs = require('node:fs')
const path = require('node:path')
const { createHash, randomUUID } = require('node:crypto')
const { spawn } = require('node:child_process')
const DEV_SERVER_URL = 'http://127.0.0.1:5173/'

async function ensureDevelopmentRuntime(
  root,
  env = process.env,
  platform = process.platform,
  signal
) {
  if (env.AUTO_MAS_RUNTIME_EXE?.trim()) return
  if (platform !== 'win32') {
    throw new Error('Runtime 仅提供 Windows 版本；其他系统请使用 yarn backend 和 yarn dev:frontend')
  }

  const version = fs.readFileSync(path.join(root, '../res/runtime-version.txt'), 'utf8').trim()
  if (!/^v\d+(\.\d+)*([-+][0-9A-Za-z.-]+)?$/.test(version)) {
    throw new Error(`Runtime 版本格式无效：${version}`)
  }
  const directory = path.join(root, 'node_modules', '.cache', 'auto-mas-runtime', version)
  const runtimePath = path.join(directory, 'auto-mas-runtime.exe')
  if (fs.existsSync(runtimePath)) {
    env.AUTO_MAS_RUNTIME_EXE = runtimePath
    return
  }

  const asset = `auto-mas-runtime-${version}.exe`
  const release = `https://github.com/AUTO-MAS-Project/AUTO-MAS-Runtime/releases/download/${version}`
  async function download(name) {
    const timeout = AbortSignal.timeout(60_000)
    const response = await fetch(`${release}/${name}`, {
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    })
    if (!response.ok) throw new Error(`下载 ${name} 失败：HTTP ${response.status}`)
    return response
  }

  console.log(`[dev] 正在下载 Runtime ${version}…`)
  const sums = await (await download('SHA256SUMS.txt')).text()
  const checksum = sums
    .split(/\r?\n/)
    .map(line => line.match(/^([\da-fA-F]{64})\s+\*?(.+?)\s*$/))
    .find(match => match?.[2] === asset)?.[1]
    .toLowerCase()
  if (!checksum) throw new Error(`SHA256SUMS.txt 中找不到 ${asset}`)
  const binary = Buffer.from(await (await download(asset)).arrayBuffer())
  if (createHash('sha256').update(binary).digest('hex') !== checksum) {
    throw new Error(`Runtime SHA-256 校验失败：${asset}`)
  }

  fs.mkdirSync(directory, { recursive: true })
  const temporary = path.join(directory, `.${randomUUID()}.tmp`)
  try {
    fs.writeFileSync(temporary, binary, { flag: 'wx' })
    fs.renameSync(temporary, runtimePath)
  } finally {
    fs.rmSync(temporary, { force: true })
  }
  env.AUTO_MAS_RUNTIME_EXE = runtimePath
  console.log(`[dev] Runtime ${version} 已准备完成`)
}

if (typeof module !== 'undefined') module.exports = { ensureDevelopmentRuntime }

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
  const runtimeDownload = new AbortController()

  async function close(code = 0) {
    process.exitCode = Math.max(process.exitCode ?? 0, code)
    closing = true
    runtimeDownload.abort()
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
    if (!process.argv.includes('--connect-existing-backend')) {
      try {
        await ensureDevelopmentRuntime(root, process.env, process.platform, runtimeDownload.signal)
      } catch (error) {
        if (!runtimeDownload.signal.aborted) throw error
        return
      }
      if (closing) return
    }
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
          // Windows 下隐藏 Electron 进程会让主窗口首次 show() 失效。
          windowsHide: false,
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
