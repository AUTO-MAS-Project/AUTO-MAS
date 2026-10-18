import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  useCommunityActivityApi,
  type ActivitySnapshot,
} from '@/views/gamesign/useCommunityActivityApi'

/** 首页和社区页共用一次查询；切页不丢快照，也不重复占用后端查询锁。 */
export const useCommunityActivityStore = defineStore('communityActivity', () => {
  const snapshots = ref<ActivitySnapshot[]>([])
  const loading = ref(false)
  const hasLoaded = ref(false)
  const errorMessage = ref('')
  const { queryActivity } = useCommunityActivityApi()
  let pending: Promise<void> | null = null

  const load = (): Promise<void> => {
    if (pending) return pending

    // 重新进入页面时保留旧快照并更新，避免账号或便笺开关变动后长期显示旧数据。
    loading.value = true
    errorMessage.value = ''
    pending = (async () => {
      try {
        snapshots.value = await queryActivity()
        hasLoaded.value = true
      } catch (error) {
        // 保留上次成功数据；首次失败也保留错误状态供页面提供重试。
        errorMessage.value = error instanceof Error ? error.message : String(error)
      } finally {
        loading.value = false
        pending = null
      }
    })()
    return pending
  }

  return { snapshots, loading, hasLoaded, errorMessage, load }
})
