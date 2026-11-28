import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useGameBindingQuery, useGamesApi } from './useGamesApi'

/** 专项管理工具与路径展示复用相同的托管默认、账号覆盖规则。 */
export function useBoundGameTarget() {
  const route = useRoute()
  const api = useGamesApi()
  const binding = useGameBindingQuery(
    () => String(route.params.scriptId ?? ''),
    () => (route.params.userId ? String(route.params.userId) : undefined)
  )
  const target = computed(() => {
    const data = binding.data.value
    const value = data?.binding?.game_id === '-' ? data.inherited : data?.binding
    return api.rows.value.find(row => row.uid === value?.game_id)
  })
  return {
    target,
    executable: computed(() => target.value?.document.info?.path ?? ''),
    launcher: computed(() => {
      const info = target.value?.document.info
      return info && 'launch_path' in info ? (info.launch_path ?? '') : ''
    }),
  }
}
