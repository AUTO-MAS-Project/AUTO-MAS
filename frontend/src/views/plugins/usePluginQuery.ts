import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getApiErrorMessage } from '@/utils/apiError'

/** 插件页面读取复用应用 QueryClient；命令不进入读取重试。 */
export function usePluginQuery<T>(
  key: MaybeRefOrGetter<readonly unknown[]>,
  request: () => Promise<T>,
  fallback: () => string
) {
  // 为插件页面封装手动触发的 Vue Query 查询，统一数据、加载状态、错误文本和重试入口。
  const query = useQuery({
    queryKey: computed(() =>
      /* 展开引用或 getter 形式的查询键，跟随页面身份与语言变化。 */ toValue(key)
    ),
    queryFn: request,
    enabled: false,
  })
  const execute = async () => {
    // 执行一次查询刷新，成功返回数据，失败返回空值并由查询状态保留错误。
    const result = await query.refetch()
    return result.error ? null : (result.data ?? null)
  }
  return {
    loading: query.isFetching,
    error: computed(() =>
      /* 将当前查询异常转换为页面可展示文本，没有异常时清除错误。 */ query.error.value
        ? getApiErrorMessage(query.error.value, fallback())
        : null
    ),
    data: query.data,
    execute,
  }
}
