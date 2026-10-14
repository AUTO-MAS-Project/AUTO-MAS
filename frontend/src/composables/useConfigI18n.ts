import { useI18n } from 'vue-i18n'
import { useBackendI18nStore } from '@/stores/backendI18n'

/** 字段键由配置类型、分组和字段组成；插件词表先于宿主通用词表。 */
export function useConfigI18n() {
  const { t, te, locale } = useI18n()
  const resources = useBackendI18nStore()
  const text = (suffix: string, fallback = '') => {
    const key = resources.pluginNames
      .map(name => `plugins.${name}.config.${suffix}`)
      .concat(`core.config.${suffix}`)
      .find(candidate => te(candidate, locale.value))
    return key ? t(key) : fallback
  }
  const fieldText = (
    type: string,
    group: string,
    field: string,
    kind: 'label' | 'tip',
    fallback = ''
  ) => text(`${type}.${group}.${field}.${kind}`, fallback)
  return { text, fieldText }
}
