import type { OutBase } from '@/api/models/OutBase'
import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'

export type UpdateDownloadSnapshotStatus =
  | 'idle'
  | 'downloading'
  | 'switchingSource'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface UpdateDownloadSnapshot {
  status: UpdateDownloadSnapshotStatus
  version: string | null
  source: string | null
  downloaded_size: number
  file_size: number
  speed: number
  file: string | null
  message: string | null
}

const postAction = (url: string) => request<OutBase>(OpenAPI, { method: 'POST', url })

export const updateDownloadApi = {
  status: () =>
    request<UpdateDownloadSnapshot>(OpenAPI, {
      method: 'GET',
      url: '/api/update/download/status',
    }),
  cancel: () => postAction('/api/update/cancel-download'),
  switchToCnb: () => postAction('/api/update/switch-to-cnb'),
}
