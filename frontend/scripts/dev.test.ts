import { fork } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { expect, test, vi } from 'vite-plus/test'

const require = createRequire(import.meta.url)
const launcher = fileURLToPath(new URL('./dev.cjs', import.meta.url))
const { ensureDevelopmentRuntime, buildDesktopEnvironment } = require(launcher) as {
  ensureDevelopmentRuntime: (
    root: string,
    env: NodeJS.ProcessEnv,
    platform: string
  ) => Promise<void>
  buildDesktopEnvironment: (baseEnv: NodeJS.ProcessEnv, preloadFile?: string) => NodeJS.ProcessEnv
}

test('buildDesktopEnvironment strips ELECTRON_RUN_AS_NODE case-insensitively while preserving dev vars', () => {
  const env = buildDesktopEnvironment(
    { ELECTRON_RUN_AS_NODE: '1', electron_run_as_node: '1', AUTO_MAS_HTTP_PORT: '36164' },
    'E:\\desktop\\AUTO-MAS\\frontend\\scripts\\dev.cjs'
  )
  expect(env.ELECTRON_RUN_AS_NODE).toBeUndefined()
  expect(env.electron_run_as_node).toBeUndefined()
  expect(env.AUTO_MAS_HTTP_PORT).toBe('36164')
  expect(env.VITE_DEV_SERVER_URL).toBe('http://127.0.0.1:5173/')
  expect(env.NODE_OPTIONS).toContain('--require "E:/desktop/AUTO-MAS/frontend/scripts/dev.cjs"')
})

test('development Runtime is verified on first download and reused offline', async () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'auto-mas-dev-runtime-'))
  const root = path.join(directory, 'frontend')
  const binary = Buffer.from('runtime fixture')
  const checksum = createHash('sha256').update(binary).digest('hex')
  const fetchMock = vi.fn(async (url: string) =>
    url.endsWith('SHA256SUMS.txt')
      ? new Response(`${checksum}  auto-mas-runtime-v1.2.3.exe\n`)
      : new Response(binary)
  )
  vi.stubGlobal('fetch', fetchMock)
  try {
    const { mkdirSync } = await import('node:fs')
    mkdirSync(path.join(directory, 'res'))
    writeFileSync(path.join(directory, 'res/runtime-version.txt'), 'v1.2.3\n')
    const first: NodeJS.ProcessEnv = {}
    await ensureDevelopmentRuntime(root, first, 'win32')
    expect(readFileSync(first.AUTO_MAS_RUNTIME_EXE!)).toEqual(binary)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const second: NodeJS.ProcessEnv = {}
    await ensureDevelopmentRuntime(root, second, 'win32')
    expect(second.AUTO_MAS_RUNTIME_EXE).toBe(first.AUTO_MAS_RUNTIME_EXE)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const custom = { AUTO_MAS_RUNTIME_EXE: 'my-runtime.exe' }
    await ensureDevelopmentRuntime(root, custom, 'win32')
    expect(custom.AUTO_MAS_RUNTIME_EXE).toBe('my-runtime.exe')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  } finally {
    vi.unstubAllGlobals()
    rmSync(directory, { recursive: true, force: true })
  }
})

test('a Runtime with an incorrect checksum is not cached', async () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'auto-mas-dev-runtime-'))
  const root = path.join(directory, 'frontend')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('SHA256SUMS.txt')
        ? new Response(`${'0'.repeat(64)}  auto-mas-runtime-v1.2.3.exe\n`)
        : new Response('wrong binary')
    )
  )
  try {
    const { mkdirSync } = await import('node:fs')
    mkdirSync(path.join(directory, 'res'))
    writeFileSync(path.join(directory, 'res/runtime-version.txt'), 'v1.2.3\n')
    const env: NodeJS.ProcessEnv = {}
    await expect(ensureDevelopmentRuntime(root, env, 'win32')).rejects.toThrow('SHA-256')
    expect(env.AUTO_MAS_RUNTIME_EXE).toBeUndefined()
    expect(existsSync(path.join(root, 'node_modules/.cache/auto-mas-runtime/v1.2.3'))).toBe(false)
  } finally {
    vi.unstubAllGlobals()
    rmSync(directory, { recursive: true, force: true })
  }
})

test('Electron type checker exits cleanly when launcher IPC disconnects', async () => {
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
  let exited = false
  let output = ''
  let failure: Error | undefined
  child.once('exit', () => (exited = true))
  child.stdout?.on('data', data => (output += data))
  child.stderr?.on('data', data => (output += data))
  child.on('error', error => (failure = error))
  try {
    await vi.waitFor(
      () => {
        if (failure) throw failure
        expect(output).toMatch(/Found 0 errors/)
      },
      { timeout: 10_000 }
    )
    expect(existsSync(path.join(directory, 'probe.js'))).toBe(false)
    child.disconnect()
    await vi.waitFor(
      () => {
        expect(exited).toBe(true)
        expect(child.exitCode).toBe(0)
      },
      { timeout: 5_000 }
    )
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill()
    }
    await vi.waitFor(() => expect(exited).toBe(true), { timeout: 5_000 })
    rmSync(directory, { recursive: true, force: true })
  }
}, 30_000)
