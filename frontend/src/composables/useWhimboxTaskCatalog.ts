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

  /** 拉取任务目录；失败时保留旧数据并给出提示，返回是否成功 */
  const fetchCatalog = async (scriptId: string): Promise<boolean> => {
    loading.value = true
    error.value = null
    try {
      const response =
        await WhimboxService.getWhimboxTaskCatalogApiApiScriptsWhimboxTaskCatalogGet(scriptId)
      if (response.code !== 200) {
        const errorMsg = response.message || t('edit.whimboxCatalogFetchFailed')
        error.value = errorMsg
        message.error(errorMsg)
        return false
      }
      data.value = response.data ?? { steps: [], options: [], upstream_version: '' }
      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : t('edit.whimboxCatalogFetchFailed')
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  return { loading, error, data, fetchCatalog }
}
