import { computed, shallowRef } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { GetService, type ScriptStatusOverviewItem } from '@/api'
import { queryRequest } from '@/utils/queryRequest'

export interface SatelliteModuleStatus {
  scheduled: boolean
  lastFailed: boolean
}

/** 卫星按配置关系聚合排期，并以组内最近的持久化历史结果显示失败。 */
export function collectSatelliteStatuses(
  scripts: readonly ScriptStatusOverviewItem[],
  keyByScriptId: ReadonlyMap<string, string>
): Map<string, SatelliteModuleStatus> {
  const result = new Map<string, SatelliteModuleStatus>()
  const latest = new Map<string, number>()
  for (const script of scripts) {
    const key = keyByScriptId.get(script.scriptId) ?? script.scriptType
    let status = result.get(key)
    if (!status) {
      status = { scheduled: false, lastFailed: false }
      result.set(key, status)
    }
    status.scheduled ||= script.scheduled === true
    const time = script.lastRunAt ? Date.parse(script.lastRunAt) : Number.NaN
    if (!Number.isFinite(time)) continue
    const previous = latest.get(key)
    if (previous === undefined || time > previous) {
      latest.set(key, time)
      status.lastFailed = script.lastFailed === true
    } else if (time === previous) {
      status.lastFailed ||= script.lastFailed === true
    }
  }
  return result
}

/** 配置／历史查询由组件已有的可见性和轮询周期触发，不订阅任务事件。 */
export function useSatelliteStatus() {
  const keyByScriptId = shallowRef<ReadonlyMap<string, string>>(new Map())
  const query = useQuery({
    queryKey: ['script-status-overview'],
    enabled: false,
    queryFn: async ({ signal }) => {
      const response = await queryRequest(signal, () =>
        GetService.getScriptStatusOverviewApiInfoScriptsStatusGet()
      )
      if (response.code !== 200) throw new Error(response.message)
      return response.data
    },
  })
  return {
    statuses: computed(() => collectSatelliteStatuses(query.data.value ?? [], keyByScriptId.value)),
    setScriptKeys: (keys: ReadonlyMap<string, string>) => {
      keyByScriptId.value = keys
    },
    refresh: async () => {
      await query.refetch({ cancelRefetch: false })
    },
  }
}
