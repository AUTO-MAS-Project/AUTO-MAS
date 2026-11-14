import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { randomUUID } from 'node:crypto'
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

export type PreparedRuntimeAlignment = (
  options: RuntimeBinaryAlignOptions
) => Promise<RuntimeBinaryAlignResult>

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
  if (check.status === 'skipped')
    return async () => /* 当前模式无需处理 Runtime 二进制时，提供直接返回跳过结果的对齐入口。 */ ({
      status: 'skipped',
    })
  if (check.status === 'unavailable' || !check.target)
    throw new Error(check.error || '无法确定 Runtime 版本')
  if (check.status === 'current')
    return async () => /* 当前 Runtime 已满足目标要求时，提供直接返回当前版本结果的对齐入口。 */ ({
      status: 'current',
      target: check.target,
    })
  const target = check.target
  const trusted = await fetchTrustedRuntimeHash(target.version)
  if (trusted.status !== 'found') throw new Error(trusted.error)
  const directory = path.join(config.dataRoot, '.frontend-updates', `runtime-${randomUUID()}`)
  await fs.mkdir(directory, { recursive: true })
  const prepared = path.join(directory, runtimeAssetName(target.version))
  let succeeded = false
  let lastError: unknown
  for (const source of buildRuntimeBinarySources(target.version)) {
    signal?.throwIfAborted()
    try {
      await downloadAndCopy(
        baseUrl,
        { url: source.url, rid: target.version, content_hash: trusted.hash },
        prepared,
        { signal }
      )
      if ((await hashFileSha256(prepared)) !== trusted.hash) throw new Error('Runtime 文件校验失败')
      succeeded = true
      break
    } catch (error) {
      if (error instanceof DownloadWriterUnconfirmed) throw error
      signal?.throwIfAborted()
      lastError = error
    }
  }
  if (!succeeded) throw lastError ?? new Error('Runtime 下载失败')
  return options =>
    /* 使用已经固定的可信版本、来源和本地材料执行二进制对齐，避免停机后重新查询下载。 */ alignRuntimeBinaryWithLatest(
      {
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
              await fs.copyFile(prepared, destination)
              return { success: true }
            },
          }),
      }
    )
}

/** 应用跨版本升级先预检；后端热更依赖检查按用户要求后补。 */
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
  try {
    const current = await client.run(['workspace', 'check'])
    if (!current.success) throw new Error(current.result.message)
    const sameVersion =
      typeof current.result.details.version === 'string' &&
      compareVersions(current.result.details.version, version) === 0
    // TODO(plugin-migration): 主流程迁移完成后补后端热更依赖预检。
    if (!sameVersion) {
      await precheckAppVersion(baseUrl, version)
    }
    signal?.throwIfAborted()
    return await prepareRuntimeBinary(config, baseUrl, version, signal)
  } finally {
    signal?.removeEventListener('abort', stop)
    await client.stop()
  }
}
