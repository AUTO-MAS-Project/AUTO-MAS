import { ref } from 'vue'
import { translate as t } from '@/i18n'
import { GetService } from '@/api'
import { getApiErrorMessage } from '@/utils/apiError'

// 安装结果以后端完成文件替换和配置落盘为准；页面只刷新设置，不二次覆盖路径。
export function useFluxdownInstallApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const fetchRelease = () => GetService.getFluxdownReleaseApiUpdateFluxdownReleaseGet()
  const installFluxdown = async (mirror: string) => {
    loading.value = true
    error.value = null
    try {
      if (!window.electronAPI?.installFluxdown) {
        throw new Error(t('core.setting.others.fluxdownInstallDesktopRequired'))
      }
      const result = await window.electronAPI.installFluxdown(mirror)
      if (result.code !== 200 || result.status === 'error') {
        throw new Error(result.message)
      }
      return result
    } catch (cause) {
      error.value = getApiErrorMessage(cause, t('core.setting.others.fluxdownInstallFailed'))
      throw new Error(error.value)
    } finally {
      loading.value = false
    }
  }
  return { loading, error, fetchRelease, installFluxdown }
}
