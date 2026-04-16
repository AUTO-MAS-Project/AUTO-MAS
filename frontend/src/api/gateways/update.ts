import {
  checkUpdateApiUpdateCheckPost,
  downloadUpdateApiUpdateDownloadPost,
  installUpdateApiUpdateInstallPost,
} from '../generated/sdk.gen'
import type { UpdateCheckIn } from '../generated/types.gen'

export const updateApi = {
  check(payload: UpdateCheckIn) {
    return checkUpdateApiUpdateCheckPost({ body: payload })
  },

  download() {
    return downloadUpdateApiUpdateDownloadPost()
  },

  install() {
    return installUpdateApiUpdateInstallPost()
  },
}
