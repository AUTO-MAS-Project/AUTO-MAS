import type { InjectionKey, Ref } from 'vue'

/** 页面仅消费刷新能力，目录与预览状态仍由 useMaaCultivation 持有。 */
export const cultivateDataRefreshKey: InjectionKey<{
  refreshing: Readonly<Ref<boolean>>
  refresh: () => Promise<'success' | 'partial' | 'cancelled'>
}> = Symbol('cultivateDataRefresh')
