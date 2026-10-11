import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = path.resolve(frontendRoot, '..')
const require = createRequire(import.meta.url)
const isPathInside = (parent, candidate) => {
  const relative = path.relative(parent, candidate)
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative))
}
const configuredTempParent = path.resolve(tmpdir())
const tempBase = isPathInside(frontendRoot, configuredTempParent)
  ? path.dirname(repositoryRoot)
  : configuredTempParent
const defaultRealRunLockPath =
  process.platform === 'win32'
    ? path.join(
        process.env.SystemRoot ?? 'C:\\Windows',
        'Temp',
        'AUTO-MAS',
        'auto-mas-e2e-real.lock'
      )
    : path.join(tempBase, 'auto-mas-e2e-real.lock')

export async function acquireRealRunLock(lockPath = defaultRealRunLockPath) {
  await mkdir(path.dirname(lockPath), { recursive: true })
  try {
    await writeFile(lockPath, `${process.pid}\n`, { flag: 'wx' })
  } catch (error) {
    if (error.code !== 'EEXIST') throw error
    let ownerPid = 0
    try {
      ownerPid = Number.parseInt((await readFile(lockPath, 'utf8')).trim(), 10)
    } catch {
      // Lock creation may still be in progress; keep the lock rather than racing it.
    }
    if (ownerPid > 0 && ownerPid !== process.pid) {
      try {
        process.kill(ownerPid, 0)
      } catch (probeError) {
        if (probeError.code === 'ESRCH') {
          // ponytail: 强制终止后的锁需人工确认；无人值守运行时再升级为租约锁。
          throw new Error('发现上次中断留下的真实 E2E 锁；确认没有真实测试运行后手动删除锁文件')
        }
      }
    }
    throw new Error('已有本机真实 E2E 正在运行，请等待其完成或清理残留锁文件')
  }
  return async () => {
    try {
      if (Number.parseInt((await readFile(lockPath, 'utf8')).trim(), 10) === process.pid) {
        await rm(lockPath, { force: true })
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error
    }
  }
}

async function main() {
  const real = process.env.AUTO_MAS_E2E_REAL === '1'
  const releaseRealRunLock = real ? await acquireRealRunLock() : undefined
  // 端到端测试直接用开发者预先调配好的真实配置：默认就是当前检出（手工调试时的 config/data/history/debug）
  const dataRoot = path.resolve(process.env.AUTO_MAS_E2E_DATA_ROOT?.trim() || repositoryRoot)
  let runRoot
  try {
    await mkdir(tempBase, { recursive: true })
    runRoot = await mkdtemp(path.join(tempBase, 'auto-mas-e2e-'))
    const tempDirectory = path.join(runRoot, 'temp')
    await mkdir(tempDirectory, { recursive: true })
    console.warn(
      `[e2e] 数据根 ${dataRoot}：测试会写入它的 config/data/history/debug，结束后不清理；请先关闭自己运行的实例`
    )
    if (real) {
      console.warn(
        '[e2e] 真实模式：会驱动该配置里的真实账号与模拟器；Notify 未剥离，可能推送真实通知；只与其它 E2E 真实运行互斥'
      )
    }
    const cli = path.join(path.dirname(require.resolve('@playwright/test/package.json')), 'cli.js')
    const child = spawn(process.execPath, [cli, 'test', ...process.argv.slice(2)], {
      cwd: frontendRoot,
      stdio: 'inherit',
      windowsHide: true,
      env: {
        ...process.env,
        TEMP: tempDirectory,
        TMP: tempDirectory,
        TMPDIR: tempDirectory,
        AUTO_MAS_E2E_DATA_ROOT: dataRoot,
        ...(real ? { PLAYWRIGHT_NO_COPY_PROMPT: '1' } : {}),
      },
    })
    // Playwright 先停止两个 webServer，父进程才可删除其工作目录。
    const interrupt = () => child.kill('SIGINT')
    process.on('SIGINT', interrupt)
    try {
      process.exitCode = await new Promise((resolve, reject) => {
        child.once('error', reject)
        child.once('exit', code => resolve(code ?? 1))
      })
    } finally {
      process.off('SIGINT', interrupt)
    }
  } finally {
    try {
      if (runRoot) {
        assert(
          path.dirname(runRoot) === tempBase &&
            path.basename(runRoot).startsWith('auto-mas-e2e-') &&
            !isPathInside(frontendRoot, runRoot),
          '拒绝清理 E2E 临时目录之外的路径'
        )
        await rm(runRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 })
      }
    } finally {
      await releaseRealRunLock?.()
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main()
}
