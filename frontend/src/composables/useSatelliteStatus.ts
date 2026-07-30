import {
  realtimeSnapshotApi,
  type ScriptDispatchState,
  type ScriptDispatchStateSnapshot,
} from '@/services/realtimeSnapshotApi'

export { getSatelliteModules } from '@/composables/satellite-config'
export type { SatelliteModule, SatelliteModuleDiscovery } from '@/composables/satellite-config'
export type { ScriptDispatchState } from '@/services/realtimeSnapshotApi'

export type SatelliteVisualStatus = 'unknown' | 'idle' | 'queued' | 'running' | 'warning' | 'failed'

export const SATELLITE_STATUS_REQUEST_TIMEOUT_MS = 8_000

export interface SatelliteModuleStatus extends ScriptDispatchState {
  visualState: SatelliteVisualStatus
}

export function resolveSatelliteVisualStatus(
  status?: ScriptDispatchState | null
): SatelliteVisualStatus {
  if (!status) return 'unknown'
  if (status.running && (status.activeFailed || status.recentFailed)) return 'warning'
  if (!status.running && status.recentFailed) return 'failed'
  if (status.running) return 'running'
  if (status.queued) return 'queued'
  return 'idle'
}

export function createSatelliteModuleStatus(status: ScriptDispatchState): SatelliteModuleStatus {
  return {
    ...status,
    visualState: resolveSatelliteVisualStatus(status),
  }
}

type CancelableStatusRequest = PromiseLike<ScriptDispatchStateSnapshot> & {
  cancel?: () => void
}

function waitForStatusResponse(
  request: CancelableStatusRequest,
  timeoutMs: number
): Promise<ScriptDispatchStateSnapshot> {
  return new Promise((resolve, reject) => {
    const timeoutId = globalThis.setTimeout(() => {
      request.cancel?.()
      reject(new Error('获取脚本运行状态超时'))
    }, timeoutMs)

    request.then(
      response => {
        globalThis.clearTimeout(timeoutId)
        resolve(response)
      },
      error => {
        globalThis.clearTimeout(timeoutId)
        reject(error)
      }
    )
  })
}

export async function getSatelliteModuleStatuses(
  timeoutMs = SATELLITE_STATUS_REQUEST_TIMEOUT_MS
): Promise<Map<string, SatelliteModuleStatus>> {
  const response = await waitForStatusResponse(realtimeSnapshotApi.getScriptStates(), timeoutMs)

  return new Map(
    Object.entries(response.states ?? {}).map(([typeKey, status]) => [
      typeKey,
      createSatelliteModuleStatus(status),
    ])
  )
}
