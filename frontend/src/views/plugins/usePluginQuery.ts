import { computed, ref, type MaybeRefOrGetter } from 'vue'
import { normalizeLocale } from '@/i18n'
import { useConfigQuery, type ConfigSnapshot } from '@/services/configUiSync'
import { getApiErrorMessage } from '@/utils/apiError'

export const pluginCatalogQueryKey = (locale: string) =>
  ['plugins', 'market', normalizeLocale(locale)] as const

/** 插件页面读取复用应用 QueryClient；命令不进入读取重试。 */
export function usePluginQuery<T extends ConfigSnapshot>(
  key: MaybeRefOrGetter<readonly unknown[]>,
  request: () => Promise<T | null>,
  fallback: () => string
) {
  // 为插件页面封装手动触发的 Vue Query 查询，统一数据、加载状态、错误文本和重试入口。
  const enabled = ref(false)
  const query = useConfigQuery({
    queryKey: key,
    queryFn: async () => {
      const value = await request()
      return { value, uiSources: value?.uiSources }
    },
    enabled,
  })
  const execute = async () => {
    // 执行一次查询刷新，成功返回数据，失败返回空值并由查询状态保留错误。
    enabled.value = true
    const result = await query.refetch({ cancelRefetch: false })
    return result.error ? null : (result.data?.value ?? null)
  }
  return {
    loading: query.isFetching,
    error: computed(() =>
      /* 将当前查询异常转换为页面可展示文本，没有异常时清除错误。 */ query.error.value
        ? getApiErrorMessage(query.error.value, fallback())
        : null
    ),
    data: computed(() => query.data.value?.value),
    execute,
  }
}
