import { ActionService, GetService, type UpdateDownloadSnapshot as DownloadSnapshot } from '@/api'
import { requestApi } from '@/utils/apiResult'

export type UpdateDownloadSnapshot = DownloadSnapshot

export const updateDownloadApi = {
  status: () => GetService.getUpdateDownloadStatusApiUpdateDownloadStatusGet(),
  cancel: () =>
    requestApi(
      () => ActionService.cancelUpdateDownloadApiUpdateCancelDownloadPost(),
      '取消下载失败'
    ),
  switchToCnb: () =>
    requestApi(
      () => ActionService.switchUpdateDownloadToCnbApiUpdateSwitchToCnbPost(),
      '切换下载源失败'
    ),
}
