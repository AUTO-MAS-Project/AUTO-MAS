import { fork } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { expect, test, vi } from 'vite-plus/test'

const require = createRequire(import.meta.url)
const launcher = fileURLToPath(new URL('./dev.cjs', import.meta.url))

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
