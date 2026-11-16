import { AdapterSetupService as Service } from '@/composables/useAdapterSetupApi'
import { type MaaCultivateImportOut } from '@/api'
import { useI18n } from 'vue-i18n'

const ERROR_KEYS: Record<string, string> = {
  format: 'core.edit.maaCultivateImportFormatError',
  empty: 'core.edit.maaCultivateImportEmpty',
  operator: 'core.edit.maaCultivateImportOperatorError',
  ambiguous: 'core.edit.maaCultivateImportAmbiguous',
  elite: 'core.edit.maaCultivateImportEliteError',
  skill: 'core.edit.maaCultivateImportSkillError',
  mastery: 'core.edit.maaCultivateImportMasteryError',
  unsupported: 'core.edit.maaCultivateImportUnsupported',
  catalog: 'core.edit.maaCultivateImportCatalogError',
}

/** 剪贴板只传公开目标文本，转换接口不写配置；保存由编辑页的队列负责。 */
export function useMaaCultivateImportApi() {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MAA养成导入')
  const formatImportError = (error: Pick<MaaCultivateImportOut, 'error' | 'index' | 'name'>) => {
    const reason = t(ERROR_KEYS[error.error ?? ''] ?? 'core.edit.maaCultivateImportFailed')
    return error.index
      ? t('core.edit.maaCultivateImportRowError', {
          index: error.index,
          name: error.name || t('core.edit.maaCultivateImportUnnamed'),
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
      throw new Error(t('core.edit.maaCultivateImportFailed'))
    }
    if (response.code !== 200) {
      throw new Error(formatImportError(response))
    }
    return { ...response, skippedMessages: (response.skipped ?? []).map(formatImportError) }
  }
  return { parseImport }
}
