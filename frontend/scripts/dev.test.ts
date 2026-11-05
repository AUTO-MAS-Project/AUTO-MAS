import { fork } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { EventEmitter } from 'node:events'
import { runInNewContext } from 'node:vm'
import { expect, test, vi } from 'vite-plus/test'

const require = createRequire(import.meta.url)
const launcher = fileURLToPath(new URL('./dev.cjs', import.meta.url))

test('relaunch from will-quit preserves arguments and waits for the launcher', () => {
  let exits = 0
  const app = Object.assign(new EventEmitter(), {
    relaunch: vi.fn(),
    quit() {
      for (const name of ['before-quit', 'will-quit']) {
        let prevented = false
        app.emit(name, { preventDefault: () => (prevented = true) })
        if (prevented) return
      }
      exits++
    },
  })
  class BrowserWindow {
    loadURL() {
      return Promise.resolve()
    }
  }
  const electron = { app, BrowserWindow }
  const moduleLoader = { _load: (_id: string) => electron }
  const child = Object.assign(new EventEmitter(), {
    versions: { electron: '43' },
    type: 'browser',
    send: vi.fn(),
  })
  runInNewContext(readFileSync(launcher, 'utf8'), {
    require: (id: string) => (id === 'node:module' ? moduleLoader : require(id)),
    process: child,
  })
  moduleLoader._load('electron')
  const options = { args: ['.', '--connect-existing-backend'] }
  let requested = false
  app.on('will-quit', () => {
    if (requested) return
    requested = true
    app.relaunch(options)
  })
  app.quit()
  expect(exits).toBe(0)
  expect(child.send).toHaveBeenCalledWith(
    { type: 'auto-mas-dev-relaunch', options },
    expect.any(Function)
  )
  child.emit('message', 'auto-mas-dev-relaunch-accepted')
  expect(exits).toBe(1)
})

test('Electron type checking reports changes without emitting and exits with its parent', async () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'auto-mas-dev-typecheck-'))
  const source = path.join(directory, 'probe.ts')
  writeFileSync(source, 'export const value: number = 1\n')
  writeFileSync(
    path.join(directory, 'tsconfig.json'),
    JSON.stringify({ compilerOptions: { strict: true, types: [] }, files: ['probe.ts'] })
  )
  const child = fork(
    require.resolve('typescript/bin/tsc'),
    ['-p', path.join(directory, 'tsconfig.json'), '--noEmit', '--watch', '--preserveWatchOutput'],
    { execArgv: ['--require', launcher], silent: true, windowsHide: true }
  )
  let output = ''
  let failure: Error | undefined
  child.stdout?.on('data', data => (output += data))
  child.stderr?.on('data', data => (output += data))
  child.on('error', error => (failure = error))
  const waitForOutput = (pattern: RegExp) =>
    vi.waitFor(
      () => {
        if (failure) throw failure
        expect(output).toMatch(pattern)
      },
      { timeout: 10_000 }
    )
  try {
    await waitForOutput(/Found 0 errors/)
    output = ''
    writeFileSync(source, 'export const value: number = "invalid"\n')
    await waitForOutput(/TS2322/)
    output = ''
    writeFileSync(source, 'export const value: number = 2\n')
    await waitForOutput(/Found 0 errors/)
    expect(existsSync(path.join(directory, 'probe.js'))).toBe(false)
    child.disconnect()
    await vi.waitFor(() => expect(child.exitCode).toBe(0), { timeout: 5_000 })
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill()
      await vi.waitFor(
        () => expect(child.exitCode !== null || child.signalCode !== null).toBe(true),
        { timeout: 5_000 }
      )
    }
    rmSync(directory, { recursive: true, force: true })
  }
}, 30_000)
