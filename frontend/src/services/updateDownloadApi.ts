import type { OutBase } from '@/api/models/OutBase'
import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'

const postAction = (url: string) => request<OutBase>(OpenAPI, { method: 'POST', url })

export const updateDownloadApi = {
  cancel: () => postAction('/api/update/cancel-download'),
  switchToCnb: () => postAction('/api/update/switch-to-cnb'),
}
