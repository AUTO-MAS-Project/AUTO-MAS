import {
  confirmNoticeApiInfoNoticeConfirmPost,
  getEmulatorComboxApiInfoComboxEmulatorPost,
  getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost,
  getGitVersionApiInfoVersionPost,
  getNoticeInfoApiInfoNoticeGetPost,
  getOverviewApiInfoGetOverviewPost,
  getPlanComboxApiInfoComboxPlanPost,
  getScriptComboxApiInfoComboxScriptPost,
  getStageComboxApiInfoComboxStagePost,
  getTaskComboxApiInfoComboxTaskPost,
  getWebConfigApiInfoWebconfigPost,
} from '../generated/sdk.gen'
import type { EmulatorIdBody, GetStageIn } from '../generated/types.gen'

export const infoApi = {
  getVersion() {
    return getGitVersionApiInfoVersionPost()
  },

  getStageOptions(payload: GetStageIn) {
    return getStageComboxApiInfoComboxStagePost({ body: payload })
  },

  getScriptOptions() {
    return getScriptComboxApiInfoComboxScriptPost()
  },

  getTaskOptions() {
    return getTaskComboxApiInfoComboxTaskPost()
  },

  getPlanOptions() {
    return getPlanComboxApiInfoComboxPlanPost()
  },

  getEmulatorOptions() {
    return getEmulatorComboxApiInfoComboxEmulatorPost()
  },

  getEmulatorDeviceOptions(payload: EmulatorIdBody) {
    return getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
      body: payload,
    })
  },

  getNotice() {
    return getNoticeInfoApiInfoNoticeGetPost()
  },

  confirmNotice() {
    return confirmNoticeApiInfoNoticeConfirmPost()
  },

  getWebConfig() {
    return getWebConfigApiInfoWebconfigPost()
  },

  getOverview() {
    return getOverviewApiInfoGetOverviewPost()
  },
}
