import { shallowRef } from 'vue'
import { useTaskRuntimeState } from '@/composables/useTaskRuntimeState'

export interface SatelliteModuleStatus {
  queued: boolean
  running: boolean
  lastFailed: boolean
}

/**
 * 各颗卫星的运行状态，按卫星键汇总：一般就是脚本类型，通用 MFW 按项目各自一颗。
 * 卫星键由 setScriptKeys 告诉它（脚本 ID → 卫星键），没登记的脚本按类型算。
 */
export function useSatelliteStatus() {
  const { scriptStatusesBy, refresh } = useTaskRuntimeState()
  const keyByScriptId = shallowRef<ReadonlyMap<string, string>>(new Map())

  return {
    statuses: scriptStatusesBy(
      identity => keyByScriptId.value.get(identity.scriptId) ?? identity.scriptType
    ),
    setScriptKeys: (keys: ReadonlyMap<string, string>) => {
      keyByScriptId.value = keys
    },
    refresh,
  }
}
