import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { Service } from '@/api'
import { queryRequest } from '@/utils/queryRequest'

/** 字符串表示托管本体；用户目标可直接传入响应式 props。 */
type ConfigLockTarget = string | { readonly scriptId: string; readonly userId: string }

export function useScriptConfigLock(target: MaybeRefOrGetter<ConfigLockTarget>) {
  const selected = computed(() => {
    const value = toValue(target)
    return typeof value === 'string' ? { scriptId: value } : value
  })
  const query = useQuery({
    queryKey: computed(() => ['script-config-lock', selected.value]),
    enabled: computed(() => !!selected.value.scriptId),
    refetchInterval: 1000,
    queryFn: async ({ signal }) => {
      const response = await queryRequest(signal, () =>
        Service.getScriptLockApiScriptsLockPost(selected.value)
      )
      if (response.code !== 200) throw new Error(response.message || '查询配置锁失败')
      return response.locked === true
    },
  })
  return { configLocked: computed(() => query.data.value === true) }
}
