import { computed } from 'vue'
import type { GameCalendarActivityInfo } from '@/api'
import {
  useActivityCompletionStore,
  type ActivityCompletionScope,
} from '@/stores/activityCompletion'

export type { ActivityCompletionScope } from '@/stores/activityCompletion'

/**
 * 活动完成状态的页面级入口。
 *
 * 实际状态存在 `useActivityCompletionStore` 里，首页活动卡与任务台共用；
 * 这里只按当前作用域（游戏 + 服务器）包一层，保持调用方现有的 API 形状。
 */
export const useActivityCompletionApi = (scope: ActivityCompletionScope) => {
  const store = useActivityCompletionStore()
  const state = computed(() => store.stateOf(scope))

  const isCompleted = (item: GameCalendarActivityInfo) => store.isCompleted(scope, item)
  const isSaving = (item: GameCalendarActivityInfo) => store.isSaving(scope, item)

  return {
    loading: computed(() => state.value.loading),
    ready: computed(() => state.value.ready),
    errorMessage: computed(() => state.value.errorMessage),
    isCompleted,
    isSaving,
    load: (force = false) => store.load(scope, force),
    toggle: (item: GameCalendarActivityInfo) => store.toggle(scope, item),
  }
}
