import {
  createEmulatorApiEmulatorPost,
  deleteEmulatorApiEmulatorEmulatorIdDelete,
  detectEmulatorsApiEmulatorDetectedGet,
  getEmulatorApiEmulatorEmulatorIdGet,
  getEmulatorStatusApiEmulatorEmulatorIdStatusGet,
  getEmulatorStatusesApiEmulatorStatusGet,
  listEmulatorsApiEmulatorGet,
  operateEmulatorApiEmulatorEmulatorIdActionsActionPost,
  updateEmulatorApiEmulatorEmulatorIdPatch,
} from '../generated/sdk.gen'
import type { EmulatorActionBody, EmulatorRead } from '../generated/types.gen'

export const emulatorApi = {
  list() {
    return listEmulatorsApiEmulatorGet()
  },

  create() {
    return createEmulatorApiEmulatorPost()
  },

  get(emulatorId: string) {
    return getEmulatorApiEmulatorEmulatorIdGet({
      path: { emulator_id: emulatorId },
    })
  },

  update(emulatorId: string, payload: EmulatorRead) {
    return updateEmulatorApiEmulatorEmulatorIdPatch({
      path: { emulator_id: emulatorId },
      body: payload,
    })
  },

  remove(emulatorId: string) {
    return deleteEmulatorApiEmulatorEmulatorIdDelete({
      path: { emulator_id: emulatorId },
    })
  },

  listDetected() {
    return detectEmulatorsApiEmulatorDetectedGet()
  },

  getAllStatuses() {
    return getEmulatorStatusesApiEmulatorStatusGet()
  },

  getStatus(emulatorId: string) {
    return getEmulatorStatusApiEmulatorEmulatorIdStatusGet({
      path: { emulator_id: emulatorId },
    })
  },

  operate(emulatorId: string, action: 'open' | 'close' | 'show', payload: EmulatorActionBody) {
    return operateEmulatorApiEmulatorEmulatorIdActionsActionPost({
      path: { emulator_id: emulatorId, action },
      body: payload,
    })
  },
}
