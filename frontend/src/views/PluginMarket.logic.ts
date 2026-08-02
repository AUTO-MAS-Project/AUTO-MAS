import type { PluginMarketSnapshot } from '@/services/pluginMarketApi'

type SnapshotCallbacks<T> = {
  load: () => Promise<T>
  apply: (snapshot: T) => void
  reportError: (error: unknown) => void
  setLoading: (loading: boolean) => void
}

export type PluginOperationKind = 'install' | 'uninstall'

export interface PendingPluginOperation {
  operation: PluginOperationKind
  package: string
  requestId: string
}

/** 仅让当前页面发起的插件操作结果结束对应 loading；全局 installed.sync 不受此表限制。 */
export class PluginOperationRequestTracker {
  private readonly pendingByPackage = new Map<string, PendingPluginOperation>()

  constructor(private readonly normalizeName: (name: string) => string) {}

  begin(operation: PluginOperationKind, packageName: string, requestId: string): void {
    const normalizedPackage = this.normalizeName(packageName)
    this.pendingByPackage.set(normalizedPackage, {
      operation,
      package: normalizedPackage,
      requestId,
    })
  }

  matches(operation: PluginOperationKind, packageName: string, requestId?: string | null): boolean {
    if (!requestId) return false
    const pending = this.pendingByPackage.get(this.normalizeName(packageName))
    return pending?.operation === operation && pending.requestId === requestId
  }

  finish(
    operation: PluginOperationKind,
    packageName: string,
    requestId?: string | null
  ): PendingPluginOperation | null {
    if (!this.matches(operation, packageName, requestId)) return null
    const normalizedPackage = this.normalizeName(packageName)
    const pending = this.pendingByPackage.get(normalizedPackage) ?? null
    this.pendingByPackage.delete(normalizedPackage)
    return pending
  }

  finishByRequestId(requestId?: string | null): PendingPluginOperation | null {
    if (!requestId) return null
    for (const [packageName, pending] of this.pendingByPackage) {
      if (pending.requestId !== requestId) continue
      this.pendingByPackage.delete(packageName)
      return pending
    }
    return null
  }

  clear(): void {
    this.pendingByPackage.clear()
  }
}

/** 合并 HTTP 刷新请求，并拒绝被后续刷新或 WS 变更淘汰的旧响应。 */
export class SnapshotRefreshCoordinator<T> {
  private revision = 0
  private loading = false
  private refreshPending = false

  refresh(callbacks: SnapshotCallbacks<T>): void {
    this.revision++
    if (this.loading) {
      this.refreshPending = true
      return
    }
    this.start(callbacks)
  }

  invalidate(): void {
    this.revision++
  }

  private start(callbacks: SnapshotCallbacks<T>): void {
    const requestRevision = this.revision
    this.loading = true
    callbacks.setLoading(true)
    void callbacks
      .load()
      .then(snapshot => {
        if (requestRevision === this.revision) {
          callbacks.apply(snapshot)
        }
      })
      .catch(error => {
        if (requestRevision === this.revision) {
          callbacks.reportError(error)
        }
      })
      .finally(() => {
        if (this.refreshPending || requestRevision !== this.revision) {
          this.refreshPending = false
          this.start(callbacks)
          return
        }
        this.loading = false
        callbacks.setLoading(false)
      })
  }
}

export const buildMarketSnapshotState = (
  snapshot: PluginMarketSnapshot,
  normalizeName: (name: string) => string
) => {
  const installedState: Record<string, boolean> = {}
  Object.entries(snapshot.installed_map || {}).forEach(([pkg, installed]) => {
    installedState[normalizeName(pkg)] = Boolean(installed)
  })
  return { snapshot, installedState }
}

export const startPluginInstall = (
  packageName: string,
  isOperationLoading: (pkg: string) => boolean,
  markOperation: (pkg: string, loading: boolean) => void,
  sendRequest: (pkg: string) => boolean
): boolean => {
  if (isOperationLoading(packageName)) {
    return false
  }
  markOperation(packageName, true)
  if (!sendRequest(packageName)) {
    markOperation(packageName, false)
    return false
  }
  return true
}
