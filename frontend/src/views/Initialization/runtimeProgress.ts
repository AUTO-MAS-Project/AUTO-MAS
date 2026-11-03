import type { NetworkActivityPayload } from './networkActivity'

const progressKeys: Record<string, string> = {
  'runtime.check': 'runtimeCheck',
  'runtime.download': 'runtimeDownload',
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

/** 只格式化已知正常阶段；未知事件、失败、取消及旧 Runtime 原文用于诊断。 */
export function formatRuntimeProgress(
  progress: NetworkActivityPayload,
  t: (key: string) => string
): string | undefined {
  const key = progress.runtimeStage && progressKeys[progress.runtimeStage]
  if (typeof key !== 'string' || !progress.runtimeStatus) return undefined
  if (progress.runtimeStatus === 'succeeded') return t('bootstrap.init.progress.finished')
  if (progress.runtimeStatus === 'skipped') return t('bootstrap.init.progress.skipped')
  if (!activeStatuses.has(progress.runtimeStatus)) return undefined
  return t(`bootstrap.init.progress.${key}`)
}
