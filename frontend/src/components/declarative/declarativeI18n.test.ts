import { describe, expect, it } from 'vite-plus/test'
import { createI18n } from 'vue-i18n'
import zhCN from '../../../../res/i18n/zh_CN.json'
import jaJP from '../../../../res/i18n/ja.json'
import { createDeclarativeI18n, type DeclarativeI18nScope } from './declarativeI18n'
import type { AppLocale } from '@/i18n'

function resolver(
  scope: DeclarativeI18nScope,
  locale: AppLocale = 'zh-CN',
  pluginMessages: Record<string, string> = {}
) {
  const messages: Record<string, Record<string, string>> = {
    'zh-CN': { ...zhCN, ...pluginMessages },
    'ja-JP': jaJP,
  }
  const { t, te } = createI18n({ legacy: false, locale, messages }).global
  return createDeclarativeI18n(t, te, locale, 'plugins.demo.config', scope)
}

describe('declarative i18n', () => {
  it('uses different common labels for managed script and account names', () => {
    expect(resolver('script').config('Info.Name.label')).toBe('托管名称')
    expect(resolver('user').config('Info.Name.label')).toBe('账号名')
  })

  it('prefers the current locale to a plugin override in a fallback locale', () => {
    const messages = { 'plugins.demo.config.Info.Name.label': '插件名称' }
    expect(resolver('script', 'ja-JP', messages).config('Info.Name.label')).toBe(
      'マネージドスクリプト名'
    )
  })

  it('prefers the scope override to the shared plugin label in the same locale', () => {
    const messages = {
      'plugins.demo.config.Info.Name.label': '共享插件名称',
      'plugins.demo.script.config.Info.Name.label': '脚本插件名称',
    }
    expect(resolver('script', 'zh-CN', messages).config('Info.Name.label')).toBe('脚本插件名称')
    expect(resolver('user', 'zh-CN', messages).config('Info.Name.label')).toBe('共享插件名称')
  })

  it('honors an empty plugin tip even with a common tip and field description', () => {
    const hint = { field: 'HardTimeLimit', description: '字段说明' }
    expect(resolver('script').tip('Run', hint)).toContain('全部重试')
    const messages = { 'plugins.demo.script.config.Run.HardTimeLimit.tip': '' }
    expect(resolver('script', 'zh-CN', messages).tip('Run', hint)).toBe('')
  })

  it('uses the field description if the tip has no translation', () => {
    const hint = { field: 'Custom', description: '字段说明' }
    expect(resolver('settings').tip('Custom', hint)).toBe('字段说明')
  })
})
