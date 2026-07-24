import { ChildProcess, spawn } from 'child_process'
import type { SpawnOptions } from 'child_process'

const MAX_CAPTURED_OUTPUT = 2 * 1024 * 1024

export interface BoundedProcessOptions {
  cwd: string
  env?: NodeJS.ProcessEnv
  timeoutMs: number
  label: string
  onStdout?: (chunk: Buffer) => void
  onStderr?: (chunk: Buffer) => void
}

export interface BoundedProcessResult {
  stdout: string
  stderr: string
}

function appendBounded(current: string, chunk: Buffer): string {
  const next = current + chunk.toString()
  return next.length <= MAX_CAPTURED_OUTPUT ? next : next.slice(-MAX_CAPTURED_OUTPUT)
}

/** Terminate the complete subprocess tree. AUTO-MAS release targets Windows. */
export function terminateProcessTree(processHandle: ChildProcess): Promise<void> {
  if (processHandle.pid == null) {
    return Promise.resolve()
  }
  if (process.platform === 'win32') {
    return new Promise((resolve, reject) => {
      const killer = spawn('taskkill.exe', ['/pid', String(processHandle.pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
        shell: false,
      })
      let finished = false
      const finish = (error?: Error) => {
        if (finished) return
        finished = true
        clearTimeout(deadline)
        killer.unref()
        if (error) reject(error)
        else resolve()
      }
      const deadline = setTimeout(() => {
        killer.kill('SIGKILL')
        finish(new Error('taskkill.exe did not exit within 5000 ms'))
      }, 5000)
      killer.once('error', error => finish(error))
      killer.once('close', code => {
        if (code === 0) finish()
        else finish(new Error(`taskkill.exe exited with code ${code ?? '<unknown>'}`))
      })
    })
  }
  processHandle.kill('SIGKILL')
  return Promise.resolve()
}

function detachStuckProcess(processHandle: ChildProcess): void {
  try {
    processHandle.kill('SIGKILL')
  } catch {
    // The caller still receives an explicit tree-did-not-exit failure.
  }
  processHandle.stdin?.destroy()
  processHandle.stdout?.destroy()
  processHandle.stderr?.destroy()
  processHandle.unref()
}

/** Run a non-shell child process with bounded logs, timeout, and process-tree termination. */
export function runBoundedProcess(
  executable: string,
  args: string[],
  options: BoundedProcessOptions
): Promise<BoundedProcessResult> {
  return new Promise((resolve, reject) => {
    const spawnOptions: SpawnOptions = {
      cwd: options.cwd,
      env: options.env,
      stdio: 'pipe',
      windowsHide: true,
      shell: false,
    }
    const child = spawn(executable, args, spawnOptions)
    let stdout = ''
    let stderr = ''
    let settled = false
    let timedOut = false
    let timeout: NodeJS.Timeout | undefined
    let killGraceTimeout: NodeJS.Timeout | undefined

    const finish = (error?: Error) => {
      if (settled) {
        return
      }
      settled = true
      if (timeout) clearTimeout(timeout)
      if (killGraceTimeout) clearTimeout(killGraceTimeout)
      if (error) {
        reject(error)
      } else {
        resolve({ stdout, stderr })
      }
    }

    child.stdout?.on('data', (chunk: Buffer) => {
      stdout = appendBounded(stdout, chunk)
      options.onStdout?.(chunk)
    })
    child.stderr?.on('data', (chunk: Buffer) => {
      stderr = appendBounded(stderr, chunk)
      options.onStderr?.(chunk)
    })
    child.on('error', error => finish(error))
    child.on('close', code => {
      if (timedOut) {
        finish(new Error(`${options.label} timed out after ${options.timeoutMs} ms`))
      } else if (code !== 0) {
        finish(
          new Error(
            `${options.label} failed with exit code ${code}: ${(stderr || stdout || 'no output').trim()}`
          )
        )
      } else {
        finish()
      }
    })

    killGraceTimeout = setTimeout(() => {
      if (timedOut) {
        detachStuckProcess(child)
        finish(new Error(`${options.label} timed out and its process tree did not exit`))
      }
    }, options.timeoutMs + 5000)
    timeout = setTimeout(() => {
      timedOut = true
      void terminateProcessTree(child).catch(() => {
        try {
          child.kill('SIGKILL')
        } catch {
          // The grace deadline detaches remaining handles.
        }
      })
    }, options.timeoutMs)
  })
}
