import { computed, ref, watch, type Ref } from 'vue'
import type { HomeModuleKey } from '@/types/home'
import type { ActivitySnapshot } from '@/views/gamesign/useCommunityActivityApi'
import { activityNoteKey, activityNoteSnapshots } from './activityNote'

/** 便笺一次只选一个角色；本次首页浏览中按游戏保留选择。 */
export const useHomeActivityNoteSelection = (
  snapshots: Ref<ActivitySnapshot[]>,
  activeKey: Ref<HomeModuleKey | null>
) => {
  const selectedKeys = ref<Partial<Record<HomeModuleKey, string>>>({})
  const notes = computed(() => activityNoteSnapshots(snapshots.value, activeKey.value))
  const selectedNote = computed(() => {
    const gameKey = activeKey.value
    if (gameKey === null) return null
    return (
      notes.value.find(snapshot => activityNoteKey(snapshot) === selectedKeys.value[gameKey]) ??
      null
    )
  })

  watch(
    notes,
    available => {
      const gameKey = activeKey.value
      if (gameKey === null) return
      const first = available[0]
      if (!first) {
        delete selectedKeys.value[gameKey]
      } else if (
        !available.some(snapshot => activityNoteKey(snapshot) === selectedKeys.value[gameKey])
      ) {
        selectedKeys.value[gameKey] = activityNoteKey(first)
      }
    },
    { immediate: true, flush: 'sync' }
  )

  const selectNote = (key: string) => {
    if (activeKey.value !== null) selectedKeys.value[activeKey.value] = key
  }

  return { notes, selectedNote, selectNote }
}
