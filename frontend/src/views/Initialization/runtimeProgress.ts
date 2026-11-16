import type { NetworkActivityPayload } from './networkActivity'

const progressKeys: Record<string, string> = {
  'runtime.check': 'runtimeCheck',
  'runtime.download': 'runtimeDownloadDetails',
  bootstrap: 'bootstrapReady',
  repair: 'runtimeRepair',
  'network.probe': 'networkProbe',
  'uv.check': 'uvCheck',
  'uv.download': 'uvDownload',
  'uv.verify': 'uvVerify',
  'workspace.check': 'workspaceCheck',
  'workspace.clone': 'workspaceClone',
  'workspace.verify': 'workspaceVerify',
  'workspace.swap': 'workspaceSwap',
  'workspace.cleanup': 'workspaceCleanup',
  'python.check': 'pythonCheck',
  'python.install': 'pythonInstall',
  'dependencies.check': 'dependenciesCheck',
  'dependencies.sync': 'dependenciesSync',
  'dependencies.rebuild': 'dependenciesRebuild',
}

const activeStatuses = new Set([
  'running',
  'pending',
  'preparing_uv',
  'syncing_repository',
  'preparing_python',
  'syncing_environment',
  'ready_to_start',
])

/**
 * 只覆盖初始化/恢复命令实际回报的正常事件。顶层状态按已确认的 stage/status 配对：
 * bootstrap --if-needed 的 ready_to_start，以及 repair 的 preparing_uv。
 * cleanup 是独立命令；doctor、握手及 backend 生命周期由各自入口处理，保留原文。
 */
export function formatRuntimeProgress(
  progress: NetworkActivityPayload,
  t: (key: string, params?: Record<string, unknown>) => string
): string | undefined {
  const key = progress.runtimeStage && progressKeys[progress.runtimeStage]
  if (typeof key !== 'string' || !progress.runtimeStatus) return undefined
  if (progress.runtimeStage === 'bootstrap' && progress.runtimeStatus !== 'ready_to_start')
    return undefined
  if (progress.runtimeStage === 'repair' && progress.runtimeStatus !== 'preparing_uv')
    return undefined
  if (progress.runtimeStage === 'dependencies.sync') {
    // 当前 Runtime 的逐源尝试及官方回退只写在 message 中，不能从测速顺序猜来源。
    // 没有下载详情时保留原文，避免通用译文遮住来源、回退事实或未知诊断。
    if (progress.runtimeStatus === 'running' && !progress.item && !progress.source) return undefined
    if (progress.runtimeStatus === 'ready_to_start')
      return t('bootstrap.init.progress.bootstrapReady')
  }
  if (progress.runtimeStatus === 'succeeded') return t('bootstrap.init.progress.finished')
  if (progress.runtimeStatus === 'skipped') return t('bootstrap.init.progress.skipped')
  if (!activeStatuses.has(progress.runtimeStatus)) return undefined
  if (progress.runtimeStage === 'runtime.download') {
    const { targetVersion, sourceName, sourceIndex, sourceCount } = progress
    // 不从中文消息猜版本或序号；任何必要字段缺省时完整保留旧事件原文。
    if (
      !targetVersion ||
      !sourceName ||
      sourceIndex === undefined ||
      sourceCount === undefined ||
      !Number.isInteger(sourceIndex) ||
      !Number.isInteger(sourceCount) ||
      sourceIndex < 1 ||
      sourceIndex > sourceCount
    )
      return undefined
    const source =
      progress.source === 'github' ? t('bootstrap.init.progress.runtimeGithubSource') : sourceName
    return t('bootstrap.init.progress.runtimeDownloadDetails', {
      version: targetVersion,
      source,
      index: sourceIndex,
      count: sourceCount,
    })
  }
  if (progress.runtimeStage === 'runtime.check' && progress.targetVersion) {
    return t('bootstrap.init.progress.runtimeCheckVersion', { version: progress.targetVersion })
  }
  return t(`bootstrap.init.progress.${key}`)
}
