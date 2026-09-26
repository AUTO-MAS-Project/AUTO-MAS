import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { WhimboxService, type WhimboxTaskCatalogData } from '@/api'
import { translate as t } from '@/i18n'

/**
 * 奇想盒一条龙任务目录：字段定义与值域完全由后端从上游三件套动态下发，
 * 前端零硬编码步骤键/值域（上游升级后目录自动跟随，MAS 发版无关）。
 */
export function useWhimboxTaskCatalog() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const data = ref<WhimboxTaskCatalogData | null>(null)
  // 并发守卫：自增请求序号，晚到的旧响应直接丢弃（对照 MaaEnd 的 sanityPlanLoadVersion）
  let fetchSeq = 0

  /** 拉取任务目录；失败时保留旧数据并给出提示，返回是否成功 */
  const fetchCatalog = async (scriptId: string): Promise<boolean> => {
    const seq = ++fetchSeq
    loading.value = true
    error.value = null
    try {
      const response =
        await WhimboxService.getWhimboxTaskCatalogApiApiScriptsWhimboxTaskCatalogGet(scriptId)
      if (seq !== fetchSeq) return false
      if (response.code !== 200) {
        const errorMsg = response.message || t('edit.whimboxCatalogFetchFailed')
        error.value = errorMsg
        message.error(errorMsg)
        return false
      }
      data.value = response.data ?? { steps: [], options: [], upstream_version: '' }
      return true
    } catch (err) {
      if (seq !== fetchSeq) return false
      const errorMsg = err instanceof Error ? err.message : t('edit.whimboxCatalogFetchFailed')
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      // 仅最新一次请求有权收 loading；旧请求晚到时不能把新请求的 loading 提前熄灭
      if (seq === fetchSeq) loading.value = false
    }
  }

  return { loading, error, data, fetchCatalog }
}
