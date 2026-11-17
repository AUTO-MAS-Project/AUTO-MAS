import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { compareVersions } from './updateVersion'
import { downloadAndCopy, DownloadWriterUnconfirmed } from './backendDownloadService'
import {
  alignRuntimeBinaryWithLatest,
  buildRuntimeBinarySources,
  checkRuntimeBinaryLatest,
  fetchTrustedRuntimeHash,
  hashFileSha256,
  runtimeAssetName,
  syncRuntimeBinary,
  type RuntimeBinaryAlignOptions,
  type RuntimeBinaryAlignResult,
} from './runtimeBinaryService'
import { resolveRuntimeReleaseChannel } from './runtimeReleaseService'
import { createRuntimeClient, type RuntimeLaunchConfig } from './runtime'
import { precheckAppVersion } from './appUpdateService'
import { UpdateMaterial } from './updateStaging'

export interface PreparedRuntimeAlignment {
  apply(options: RuntimeBinaryAlignOptions): Promise<RuntimeBinaryAlignResult>
  dispose(): Promise<void>
}

/** 仍有后端时取得并复制 Runtime；替换阶段只读前端副本和本次可信校验信息。 */
export async function prepareRuntimeBinary(
  config: RuntimeLaunchConfig,
  baseUrl: string,
  version: string,
  signal?: AbortSignal
): Promise<PreparedRuntimeAlignment> {
  // 检查目标 Runtime 版本与可信来源，通过后端下载中心预取并复制二进制，返回停机后可执行的对齐入口。
  if (!config.runtimePath) throw new Error('找不到 Runtime 可执行文件')
  const channel = resolveRuntimeReleaseChannel(version)
  const check = await checkRuntimeBinaryLatest({
    runtimePath: config.runtimePath,
    appRoot: config.appRoot,
    channel,
  })
  if (check.status === 'skipped' || check.status === 'current') {
    return {
      async apply() {
        // 当前无需下载或已满足版本时直接返回检查结果，不创建材料目录。
        return check.status === 'skipped'
          ? { status: 'skipped' }
          : { status: 'current', target: check.target }
      },
      async dispose() {
        // 没有创建暂存文件，无需释放磁盘资源。
      },
    }
  }
  if (check.status === 'unavailable' || !check.target)
    throw new Error(check.error || '无法确定 Runtime 版本')
  const target = check.target
  const trusted = await fetchTrustedRuntimeHash(target.version)
  if (trusted.status !== 'found') throw new Error(trusted.error)
  let material: UpdateMaterial | undefined
  let prepared: string | undefined
  let lastError: unknown
  for (const source of buildRuntimeBinarySources(target.version)) {
    signal?.throwIfAborted()
    let attempt: UpdateMaterial | undefined
    try {
      attempt = await UpdateMaterial.create(config.dataRoot, 'runtime', target.version)
      const file = path.join(attempt.directory, runtimeAssetName(target.version))
      await downloadAndCopy(
        baseUrl,
        { url: source.url, rid: target.version, content_hash: trusted.hash },
        `${file}.part`,
        { signal }
      )
      if ((await hashFileSha256(`${file}.part`)) !== trusted.hash)
        throw new Error('Runtime 文件校验失败')
      signal?.throwIfAborted()
      await fs.rename(`${file}.part`, file)
      await attempt.setPhase('ready')
      signal?.throwIfAborted()
      material = attempt
      prepared = file
      break
    } catch (error) {
      if (error instanceof DownloadWriterUnconfirmed) throw error
      signal?.throwIfAborted()
      lastError = error
    } finally {
      // 每个来源有独立目录，校验失败、取消或收尾失败均释放前端副本。
      if (attempt !== material) await attempt?.dispose()
    }
  }
  if (!material || !prepared) throw lastError ?? new Error('Runtime 下载失败')
  const owned = material
  const file = prepared
  let active: Promise<RuntimeBinaryAlignResult> | undefined
  let disposed = false
  return {
    async apply(options) {
      // 会话持有完整材料；禁止释放后使用或并行对齐，并跟踪消费结束后再允许删除。
      if (disposed || active) throw new Error('Runtime 更新材料已释放或正在使用')
      active = alignRuntimeBinaryWithLatest({
        ...options,
        fetchLatest: async () => /* 向对齐流程返回准备阶段已经确认的目标版本和可信来源。 */ ({
          status: 'resolved',
          version: target.version,
          source: trusted.source,
        }),
        sync: syncOptions =>
          /* 使用准备好的摘要和本地文件执行 Runtime 二进制同步。 */ syncRuntimeBinary({
            ...syncOptions,
            fetchText: async () => /* 向同步校验提供可信来源中已确认的文件摘要与发行文件名。 */ ({
              kind: 'text',
              text: `${trusted.hash}  ${runtimeAssetName(target.version)}`,
            }),
            download: async (_url, destination) => {
              // 把前端暂存的 Runtime 二进制复制到同步流程指定的位置，不再次访问网络。
              await fs.copyFile(file, destination)
              return { success: true }
            },
          }),
      })
      try {
        return await active
      } finally {
        active = undefined
      }
    },
    async dispose() {
      // 重复释放安全；先阻止新消费，再等待正在执行的对齐和文件复制结束。
      disposed = true
      await active?.catch(() => {})
      await owned.dispose()
    },
  }
}

/** 前端在停止后端前预检目标依赖，再准备 Runtime 二进制。 */
export async function prepareCoreUpgrade(
  config: RuntimeLaunchConfig,
  baseUrl: string,
  version: string,
  signal?: AbortSignal
): Promise<PreparedRuntimeAlignment> {
  // 通过 Runtime 客户端读取目标 core 信息，调用后端兼容性预检并准备二进制对齐，结束时释放客户端。
  const client = createRuntimeClient({
    runtimePath: config.runtimePath!,
    appRoot: config.appRoot,
    dataRoot: config.dataRoot,
  })
  const stop = () => {
    // 收到取消时请求停止准备阶段使用的 Runtime 客户端。
    void client.stop()
  }
  signal?.addEventListener('abort', stop, { once: true })
  let prepared: PreparedRuntimeAlignment | undefined
  try {
    const current = await client.run(['workspace', 'check'])
    if (!current.success) throw new Error(current.result.message)
    const sameVersion =
      typeof current.result.details.version === 'string' &&
      compareVersions(current.result.details.version, version) === 0
    if (sameVersion) {
      // 同版本热更也可能改变依赖，必须检查远端候选提交，不能复用当前安装版本的依赖。
      const remote = await client.run(['workspace', 'check', '--remote'])
      if (!remote.success) throw new Error(remote.result.message)
      const commit = remote.result.details.remoteCommit
      if (typeof commit !== 'string' || !/^[a-f0-9]{40}$/i.test(commit))
        throw new Error('Runtime 未返回有效的更新提交，无法检查插件兼容性')
      await precheckAppVersion(baseUrl, version, commit, signal)
      // TODO(plugin-migration): Runtime 支持固定目标提交后，对齐预检与实际更新对象。
    } else {
      await precheckAppVersion(baseUrl, version, undefined, signal)
    }
    signal?.throwIfAborted()
    prepared = await prepareRuntimeBinary(config, baseUrl, version, signal)
  } finally {
    signal?.removeEventListener('abort', stop)
    await client.stop().catch(async error => {
      // 客户端未能收尾或准备末尾收到取消时，材料不能脱离返回对象而泄漏。
      await prepared?.dispose()
      throw error
    })
    if (signal?.aborted) await prepared?.dispose()
  }
  signal?.throwIfAborted()
  return prepared
}
