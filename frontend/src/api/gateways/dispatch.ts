import {
  addTaskApiDispatchStartPost,
  cancelPowerTaskApiDispatchCancelPowerPost,
  getPowerApiDispatchGetPowerPost,
  setPowerApiDispatchSetPowerPost,
  stopTaskApiDispatchStopPost,
} from '../generated/sdk.gen'
import type { DispatchIn, PowerIn, TaskCreateIn } from '../generated/types.gen'

export const dispatchApi = {
  startTask(payload: TaskCreateIn) {
    return addTaskApiDispatchStartPost({ body: payload })
  },

  stopTask(payload: DispatchIn) {
    return stopTaskApiDispatchStopPost({ body: payload })
  },

  getPower() {
    return getPowerApiDispatchGetPowerPost()
  },

  setPower(payload: PowerIn) {
    return setPowerApiDispatchSetPowerPost({ body: payload })
  },

  cancelPowerTask() {
    return cancelPowerTaskApiDispatchCancelPowerPost()
  },
}
