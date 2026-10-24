import { computed, ref } from 'vue'
import { queryOptions, useQuery, useQueryClient } from '@tanstack/vue-query'
import { Service, type EmulatorConfig_Info } from '@/api'
import { translate as t } from '@/i18n'
import { queryClient } from '@/services/queryClient'
import { queryRequest } from '@/utils/queryRequest'

const EMULATOR_QUERY_KEY = ['emulator-options'] as const
const OPTIONS_STALE_TIME_MS = 60_000
type EmulatorType = NonNullable<EmulatorConfig_Info['Type']>

const emulatorOptionsQuery = queryOptions({
  queryKey: [...EMULATOR_QUERY_KEY, 'list'],
  staleTime: OPTIONS_STALE_TIME_MS,
  meta: { notifyOnError: true },
  queryFn: async ({ signal }) => {
    const response = await queryRequest(signal, () =>
      Service.getEmulatorComboxApiInfoComboxEmulatorPost()
    )
    if (response.code !== 200) {
      throw new Error(response.message || t('edit.couldNotLoadEmulator'))
    }
    return response.data ?? []
  },
})

const emulatorTypesQuery = queryOptions({
  queryKey: [...EMULATOR_QUERY_KEY, 'types'],
  staleTime: OPTIONS_STALE_TIME_MS,
  meta: { notifyOnError: true },
  queryFn: async ({ signal }) => {
    const response = await queryRequest(signal, () => Service.getEmulatorApiEmulatorGetPost({}))
    if (response.code !== 200) {
      throw new Error(response.message || t('edit.couldNotLoadEmulator'))
    }
    const types: Record<string, EmulatorType> = {}
    for (const [id, config] of Object.entries(response.data)) {
      if (config.Info?.Type) types[id] = config.Info.Type
    }
    return types
  },
})

/** 列表与类型由各编辑页共享；MaaFW 额外等待类型信息就绪。 */
export function useEmulatorOptions({ includeTypes = false }: { includeTypes?: boolean } = {}) {
  const client = useQueryClient()
  const enabled = ref(false)
  const options = useQuery({ ...emulatorOptionsQuery, enabled })
  const types = useQuery({
    ...emulatorTypesQuery,
    enabled: computed(() => enabled.value && includeTypes),
  })

  const loadEmulatorOptions = async () => {
    enabled.value = true
    try {
      await Promise.all([
        client.fetchQuery(emulatorOptionsQuery),
        includeTypes ? client.fetchQuery(emulatorTypesQuery) : undefined,
      ])
      return true
    } catch {
      // 查询保留失败状态，公共 QueryCache 已提示；不打断编辑页其他部分的加载。
      return false
    }
  }

  return {
    emulatorOptions: computed(() => (enabled.value ? (options.data.value ?? []) : [])),
    emulatorTypeById: computed(() => types.data.value ?? {}),
    emulatorLoading: computed(
      () => enabled.value && (options.isFetching.value || (includeTypes && types.isFetching.value))
    ),
    emulatorOptionsReady: computed(
      () => enabled.value && options.isSuccess.value && (!includeTypes || types.isSuccess.value)
    ),
    loadEmulatorOptions,
    // 切到 PC / URL 只清当前页面的显示，不删除其他编辑页使用的缓存。
    clearEmulatorOptions: () => {
      enabled.value = false
    },
  }
}

export async function invalidateEmulatorOptions() {
  // 先取消旧读取，避免修改前发出的请求在保存后覆盖新列表。
  await queryClient.cancelQueries({ queryKey: EMULATOR_QUERY_KEY })
  await queryClient.invalidateQueries({ queryKey: EMULATOR_QUERY_KEY })
}
