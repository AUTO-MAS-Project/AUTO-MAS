import type { ElectronAPI } from '@/types/electron'

type ElectronAppUpdateAPI = Pick<
  ElectronAPI,
  | 'checkAppUpdate'
  | 'downloadAppUpdate'
  | 'installAppUpdate'
  | 'getAppUpdateStatus'
  | 'cancelAppUpdate'
  | 'onAppUpdateEvent'
  | 'removeAppUpdateEventListener'
>

export function getElectronAppUpdateAPI(): ElectronAppUpdateAPI {
  const primary = window.electronAPI as Partial<ElectronAppUpdateAPI> | undefined
  const fallback = window.electronAppUpdateAPI

  const api = {
    checkAppUpdate: primary?.checkAppUpdate ?? fallback?.checkAppUpdate,
    downloadAppUpdate: primary?.downloadAppUpdate ?? fallback?.downloadAppUpdate,
    installAppUpdate: primary?.installAppUpdate ?? fallback?.installAppUpdate,
    getAppUpdateStatus: primary?.getAppUpdateStatus ?? fallback?.getAppUpdateStatus,
    cancelAppUpdate: primary?.cancelAppUpdate ?? fallback?.cancelAppUpdate,
    onAppUpdateEvent: primary?.onAppUpdateEvent ?? fallback?.onAppUpdateEvent,
    removeAppUpdateEventListener:
      primary?.removeAppUpdateEventListener ?? fallback?.removeAppUpdateEventListener,
  }

  const missingMethod = Object.entries(api).find(([, value]) => typeof value !== 'function')
  if (missingMethod) {
    throw new Error(`Missing Electron app-update bridge method: ${missingMethod[0]}`)
  }

  return api as ElectronAppUpdateAPI
}
