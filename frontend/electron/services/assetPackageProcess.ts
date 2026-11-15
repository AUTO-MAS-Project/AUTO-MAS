import { utilityProcess } from 'electron'
import * as path from 'path'
import { AssetPackageError, type PackageErrorCode } from './assetPackageService'
import type * as Appearance from './appearanceService'
import type * as Mascot from './mascotPackageService'

export type PackageJob =
  | { operation: 'inspect-theme' | 'inspect-mascot'; zipPath: string }
  | {
      operation: 'import-theme' | 'import-mascot'
      zipPath: string
      userDataPath: string
      replace: boolean
    }

export type PackageReply =
  | {
      operation: 'inspect-theme'
      value: Awaited<ReturnType<typeof Appearance.inspectAppearancePackage>>
    }
  | { operation: 'inspect-mascot'; value: Awaited<ReturnType<typeof Mascot.inspectMascotPackage>> }
  | {
      operation: 'import-theme'
      value: Awaited<ReturnType<typeof Appearance.importAppearancePackage>>
    }
  | { operation: 'import-mascot'; value: Awaited<ReturnType<typeof Mascot.importMascotPackage>> }
  | { operation: 'error'; code: PackageErrorCode; error: string }

let queue: Promise<void> = Promise.resolve()
let quitting = false

/** 仅由用户确认后的退出收尾调用，等资源写入完成后才允许 Electron 退出。 */
export async function finishAssetPackageJobs(): Promise<void> {
  quitting = true
  await queue
}

/** 大包只在资源进程中展开；队列同时只有一个写入者，主进程异步等待处理结果。 */
async function run(job: PackageJob): Promise<PackageReply> {
  const task = queue.then(
    () =>
      new Promise<PackageReply>((resolve, reject) => {
        if (quitting) {
          reject(new AssetPackageError('PROCESS_FAILED', '应用正在退出'))
          return
        }
        const child = utilityProcess.fork(path.join(__dirname, 'assetPackageWorker.js'), [], {
          serviceName: '资源包处理',
          stdio: 'ignore',
        })
        let reply: PackageReply | undefined
        child.once('spawn', () => child.postMessage(job))
        child.on('error', () => {
          /* 等待 exit，避免把仍在写盘的任务当作已结束。 */
        })
        child.once('message', (message: PackageReply) => {
          reply = message
          child.kill()
        })
        child.once('exit', () => {
          if (reply) resolve(reply)
          else reject(new AssetPackageError('PROCESS_FAILED', '资源包处理进程已退出'))
        })
      })
  )
  queue = task.then(
    () => undefined,
    () => undefined
  )
  const reply = await task
  if (reply.operation === 'error') throw new AssetPackageError(reply.code, reply.error)
  return reply
}

export async function inspectAppearancePackage(zipPath: string) {
  const reply = await run({ operation: 'inspect-theme', zipPath })
  if (reply.operation !== 'inspect-theme') throw new Error('资源包处理结果不匹配')
  return reply.value
}

export async function inspectMascotPackage(zipPath: string) {
  const reply = await run({ operation: 'inspect-mascot', zipPath })
  if (reply.operation !== 'inspect-mascot') throw new Error('资源包处理结果不匹配')
  return reply.value
}

export async function importAppearancePackage(
  userDataPath: string,
  zipPath: string,
  replace = false
): Promise<Awaited<ReturnType<typeof Appearance.importAppearancePackage>>> {
  try {
    const reply = await run({ operation: 'import-theme', userDataPath, zipPath, replace })
    if (reply.operation !== 'import-theme') throw new Error('资源包处理结果不匹配')
    return reply.value
  } catch (error) {
    return {
      success: false,
      code: 'PROCESS_FAILED' as const,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

export async function importMascotPackage(
  userDataPath: string,
  zipPath: string,
  replace = false
): Promise<Awaited<ReturnType<typeof Mascot.importMascotPackage>>> {
  try {
    const reply = await run({ operation: 'import-mascot', userDataPath, zipPath, replace })
    if (reply.operation !== 'import-mascot') throw new Error('资源包处理结果不匹配')
    return reply.value
  } catch (error) {
    return {
      success: false,
      code: 'PROCESS_FAILED' as const,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
