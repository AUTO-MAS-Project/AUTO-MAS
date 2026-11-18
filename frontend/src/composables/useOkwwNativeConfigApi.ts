import type { OkwwPanelKind } from '@/types/nativeConfig'
import { useI18n } from 'vue-i18n'
import { Service, OkwwTaskConfigIn } from '@/api'
import { observeFeature, apiOutcome } from '@/utils/featureAnalytics'
export function useOkwwNativeConfigApi() {
  const { locale } = useI18n()
  async function readConfig(scriptId: string, userId: string, kind: OkwwPanelKind) {
    const response = await Service.getOkwwTaskConfigApiApiScriptsOkwwTaskConfigGet(
      scriptId,
      userId,
      kind,
      locale.value.startsWith('zh') ? 'zh_CN' : locale.value.startsWith('ja') ? 'ja_JP' : 'en_US'
    )
    if (response.code !== 200) throw new Error(response.message || '无法读取配置')
    return response
  }
  async function saveConfig(
    scriptId: string,
    userId: string,
    kind: OkwwPanelKind,
    values: Record<string, unknown>
  ) {
    const response = await observeFeature(
      'adapter_setup_finished',
      { script_type: 'Okww', operation_kind: 'save', engine_kind: 'unknown' },
      () =>
        Service.saveOkwwTaskConfigApiApiScriptsOkwwTaskConfigPost({
          scriptId,
          userId,
          kind: {
            daily: OkwwTaskConfigIn.kind.DAILY,
            echo: OkwwTaskConfigIn.kind.ECHO,
            nightmare: OkwwTaskConfigIn.kind.NIGHTMARE,
            combat: OkwwTaskConfigIn.kind.COMBAT,
            character: OkwwTaskConfigIn.kind.CHARACTER,
            monthly: OkwwTaskConfigIn.kind.MONTHLY,
          }[kind],
          values,
        }),
      apiOutcome
    )
    if (response.code !== 200) throw new Error(response.message || '配置保存失败')
  }
  return { readConfig, saveConfig }
}
