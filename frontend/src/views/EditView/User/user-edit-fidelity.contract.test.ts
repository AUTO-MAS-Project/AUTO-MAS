import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname)
const readUserEditor = (name: string) => readFileSync(resolve(root, name), 'utf8')
const configEditor = readFileSync(
  resolve(root, '../../OkScriptUserEdit/OkScriptConfigEditor.vue'),
  'utf8'
)

describe('通用与插件用户编辑功能保真', () => {
  it.each(['GenericUserEdit.vue', 'PluginUserEdit.vue'])(
    '%s 保留 schema action、会话和敏感字段安全保存链',
    file => {
      const source = readUserEditor(file)

      expect(source).toContain('HeaderSchemaActionButton')
      expect(source).toContain('SchemaActionSessionMask')
      expect(source).toContain('runFieldAction')
      expect(source).toContain('buildSchemaSavePayload')
      expect(source).toContain('resetSensitiveDrafts')
      expect(source).toContain('sanitizeErrorForLog')
      expect(source).toContain('updateResult === false')
      expect(source).toContain('saveError.value')
    }
  )

  it('插件用户页保留插件 JSON 文件编辑器、文档和热更新刷新链', () => {
    const source = readUserEditor('PluginUserEdit.vue')

    expect(source).toContain('<PluginJsonConfigEditor')
    expect(source).toContain('pluginConfigEditor.endpointPrefix')
    expect(source).toContain('v-if="docsUrl"')
    expect(source).toContain("subscribe({ id: 'PluginSystem' }")
    expect(source).toContain('refreshSchemaFromPluginSystem')
  })
})

describe('ok-script 与 ok-ww 用户编辑功能保真', () => {
  it.each(['OkScriptUserEdit.vue', 'OkwwUserEdit.vue'])(
    '%s 保留项目配置、额外脚本、通知与 Webhook',
    file => {
      const source = readUserEditor(file)

      expect(source).toContain('<OkScriptConfigEditor')
      expect(source).toContain('<ExtraScriptSection')
      expect(source).toContain('<WebhookManager')
      expect(source).toContain('handleTaskIndexChange')
      expect(source).toContain('Notify.IfSendMail')
      expect(source).toContain('Notify.IfServerChan')
      expect(source).toContain('saveError.value')
    }
  )

  it('手写敏感字段不回填，空白失焦不会清除已保存值', () => {
    const okScript = readUserEditor('OkScriptUserEdit.vue')
    const okww = readUserEditor('OkwwUserEdit.vue')

    expect(okScript).toContain("ServerChanKey: ''")
    expect(okScript).toContain("key === 'Notify.ServerChanKey' && !String(value || '').trim()")
    expect(okScript).toContain("serverChanKeyConfigured ? '已配置，留空保持不变'")

    expect(okww).toContain("Password: ''")
    expect(okww).toContain("ServerChanKey: ''")
    expect(okww).toContain("key === 'Info.Password' || key === 'Notify.ServerChanKey'")
    expect(okww).toContain("passwordConfigured ? '已配置，留空保持不变'")
    expect(okww).toContain("serverChanKeyConfigured ? '已配置，留空保持不变'")
  })

  it('已保存敏感字段提供明确且可确认的清空入口', () => {
    const okScript = readUserEditor('OkScriptUserEdit.vue')
    const okww = readUserEditor('OkwwUserEdit.vue')

    expect(okScript).toContain('confirmClearServerChanKey')
    expect(okScript).toContain("Notify: { ServerChanKey: '' }")
    expect(okScript).toContain('清空原值')

    expect(okww).toContain('confirmClearSensitiveField')
    expect(okww).toContain("type OkwwSensitiveField = 'Info.Password' | 'Notify.ServerChanKey'")
    expect(okww).toContain("[group]: { [field]: '' }")
    expect(okww).toContain('清空原值')
  })

  it('所有布尔保存结果都被检查，失败进入显式错误状态', () => {
    const okScript = readUserEditor('OkScriptUserEdit.vue')
    const okww = readUserEditor('OkwwUserEdit.vue')

    expect(okScript).toContain('if (!saved)')
    expect(okScript).toContain("throw new Error('用户配置保存失败，请检查后端连接')")
    expect(okScript).toContain("throw new Error('任务配置保存失败，请检查后端连接')")
    expect(okww).toContain('updateResult === false')
    expect(okww).toContain("throw new Error('用户配置保存失败，请检查后端连接')")
  })
})

describe('用户编辑 macOS 单层表面契约', () => {
  it.each([
    'GenericUserEdit.vue',
    'PluginUserEdit.vue',
    'OkScriptUserEdit.vue',
    'OkwwUserEdit.vue',
  ])('%s 使用紧凑页头和单层磨砂表面', file => {
    const source = readUserEditor(file)

    expect(source).toContain('<PageHeader')
    expect(source).toContain('compact')
    expect(source).toContain('transparent')
    expect(source).not.toContain('<a-card')
    expect(source).toMatch(/class="(?:user-edit-surface|config-surface)"/)
    expect(source).toContain('var(--v6-vibrancy-material)')
    expect(source).toContain("data-perf-mode='low'")
  })

  it('配置文件编辑器保留文件选择、JSON 字段和显式保存/失败重试状态', () => {
    expect(configEditor).toContain('selectConfig(config.filename)')
    expect(configEditor).toContain("field.type === 'json'")
    expect(configEditor).toContain('formatJsonValue')
    expect(configEditor).toContain('@click="saveAll(false)"')
    expect(configEditor).toContain('v-if="saveError"')
    expect(configEditor).toContain('return false')
    expect(configEditor).toContain('if (!saved) return')
  })
})
