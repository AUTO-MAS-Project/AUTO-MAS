import { AdapterSetupService as Service } from '@/composables/useAdapterSetupApi'
import { type MaaCultivateImportOut } from '@/api'
import { useI18n } from 'vue-i18n'

const ERROR_KEYS: Record<string, string> = {
  format: 'plugins.maa_adapter.edit.maaCultivateImportFormatError',
  empty: 'plugins.maa_adapter.edit.maaCultivateImportEmpty',
  operator: 'plugins.maa_adapter.edit.maaCultivateImportOperatorError',
  ambiguous: 'plugins.maa_adapter.edit.maaCultivateImportAmbiguous',
  elite: 'plugins.maa_adapter.edit.maaCultivateImportEliteError',
  skill: 'plugins.maa_adapter.edit.maaCultivateImportSkillError',
  mastery: 'plugins.maa_adapter.edit.maaCultivateImportMasteryError',
  unsupported: 'plugins.maa_adapter.edit.maaCultivateImportUnsupported',
  catalog: 'plugins.maa_adapter.edit.maaCultivateImportCatalogError',
}

/** 剪贴板只传公开目标文本，转换接口不写配置；保存由编辑页的队列负责。 */
export function useMaaCultivateImportApi() {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MAA养成导入')
  const formatImportError = (error: Pick<MaaCultivateImportOut, 'error' | 'index' | 'name'>) => {
    const reason = t(
      ERROR_KEYS[error.error ?? ''] ?? 'plugins.maa_adapter.edit.maaCultivateImportFailed'
    )
    return error.index
      ? t('plugins.maa_adapter.edit.maaCultivateImportRowError', {
          index: error.index,
          name: error.name || t('plugins.maa_adapter.edit.maaCultivateImportUnnamed'),
          reason,
        })
      : reason
  }
  const parseImport = async (
    scriptId: string,
    content: string
  ): Promise<MaaCultivateImportOut & { skippedMessages: string[] }> => {
    let response: MaaCultivateImportOut
    try {
      response = await Service.parseMaaCultivateImportApiScriptsMaaCultivateImportPost({
        scriptId,
        content,
      })
    } catch (error) {
      logger.error(`养成导入请求失败: ${error instanceof Error ? error.message : String(error)}`)
      throw new Error(t('plugins.maa_adapter.edit.maaCultivateImportFailed'))
    }
    if (response.code !== 200) {
      throw new Error(formatImportError(response))
    }
    return { ...response, skippedMessages: (response.skipped ?? []).map(formatImportError) }
  }
  return { parseImport }
}
