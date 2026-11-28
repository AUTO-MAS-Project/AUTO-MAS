import { ref } from 'vue'
import { defineStore } from 'pinia'
import { isPluginUnavailable } from '@/services/signflowApi'
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
  // 失败原因是「便笺插件没装」时单独留一个信号：文案只会让人知道坏了，页面得给出安装入口。
  const pluginMissing = ref(false)
  const { queryActivity } = useCommunityActivityApi()
  let pending: Promise<void> | null = null

  const load = (): Promise<void> => {
    if (pending) return pending

    // 重新进入页面时保留旧快照并更新，避免账号或便笺开关变动后长期显示旧数据。
    loading.value = true
    errorMessage.value = ''
    pluginMissing.value = false
    pending = (async () => {
      try {
        snapshots.value = await queryActivity()
        hasLoaded.value = true
      } catch (error) {
        // 保留上次成功数据；首次失败也保留错误状态供页面提供重试。
        // 插件未启用的判定复用 services 里的唯一实现，不在页面各自比对文案。
        pluginMissing.value = isPluginUnavailable(error)
        errorMessage.value = error instanceof Error ? error.message : String(error)
      } finally {
        loading.value = false
        pending = null
      }
    })()
    return pending
  }

  return { snapshots, loading, hasLoaded, errorMessage, pluginMissing, load }
})
