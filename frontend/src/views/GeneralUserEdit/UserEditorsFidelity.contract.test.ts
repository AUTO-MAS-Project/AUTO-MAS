import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const moduleDir = dirname(fileURLToPath(import.meta.url))
const viewsDir = resolve(moduleDir, '..')
const userEditorDir = resolve(viewsDir, 'EditView/User')
const srcEditorDir = resolve(viewsDir, 'SRCUserEdit')

const readUserEditor = (name: string) => readFileSync(resolve(userEditorDir, name), 'utf8')
const readSrcEditor = (name: string) => readFileSync(resolve(srcEditorDir, name), 'utf8')

describe('General / HSR / SRC 用户编辑功能与 UI 契约', () => {
  const generalSource = readUserEditor('GeneralUserEdit.vue')
  const hsrSource = readUserEditor('HSRUserEdit.vue')
  const srcSource = readUserEditor('SRCUserEdit.vue')
  const srcBasicSource = readSrcEditor('BasicInfoSection.vue')
  const srcNotifySource = readSrcEditor('NotifyConfigSection.vue')
  const srcHeaderSource = readSrcEditor('SRCUserEditHeader.vue')

  it('保留配置会话、阶段、培养入口、额外脚本和通知功能', () => {
    expect(generalSource).toContain('handleGeneralConfig')
    expect(generalSource).toContain('handleSaveGeneralConfig')
    expect(generalSource).toContain('<ExtraScriptSection')
    expect(generalSource).toContain('<WebhookManager')

    expect(hsrSource).toContain('getCapabilities')
    expect(hsrSource).toContain('getStageOptions')
    expect(hsrSource).toContain('<StageConfigSection')
    expect(hsrSource).toContain('DivergentUniverse')
    expect(hsrSource).toContain('CurrencyWars')
    expect(hsrSource).toContain("getTaskMapping('ReceiveRewards')")

    expect(srcSource).toContain('handleSRCConfig')
    expect(srcSource).toContain('handleSaveSRCConfig')
    expect(srcSource).toContain('<StageConfigSection')
    expect(srcSource).toContain('<ExtraScriptSection')
    expect(srcSource).toContain('<NotifyConfigSection')
  })

  it('敏感字段只绑定空草稿，不把后端返回值回填输入', () => {
    expect(generalSource).toContain(':value="serverChanKeyDraft"')
    expect(generalSource).not.toContain('v-model:value="formData.Notify.ServerChanKey"')
    expect(generalSource).toContain("ServerChanKey: '',")

    expect(hsrSource).toContain(':value="sraIdDraft"')
    expect(hsrSource).toContain(':value="sraPasswordDraft"')
    expect(hsrSource).not.toContain('v-model:value="formData.SRA.Id"')
    expect(hsrSource).not.toContain('v-model:value="formData.SRA.Password"')
    expect(hsrSource).toContain("Id: '',")
    expect(hsrSource).toContain("Password: '',")

    expect(srcBasicSource).toContain(':value="passwordDraft"')
    expect(srcBasicSource).not.toContain('v-model:value="formData.Info.Password"')
    expect(srcNotifySource).toContain(':value="serverChanKeyDraft"')
    expect(srcNotifySource).not.toContain('v-model:value="formData.Notify.ServerChanKey"')
    expect(srcSource).toContain("Password: ''")
    expect(srcSource).toContain("ServerChanKey: ''")
  })

  it('空草稿不会在 blur 时误清原值，替换和清空必须明确操作', () => {
    expect(generalSource).not.toContain(
      '@blur="handleFieldSave(\'Notify.ServerChanKey\', formData.Notify.ServerChanKey)"'
    )
    expect(generalSource).toContain('保存新值')
    expect(generalSource).toContain('清空原值')

    expect(hsrSource).not.toContain("@blur=\"handleFieldSave('SRA.Password'")
    expect(hsrSource).toContain("saveSraCredential('SRA.Id'")
    expect(hsrSource).toContain("saveSraCredential('SRA.Password'")
    expect(hsrSource).toContain('clearSraCredential')

    expect(srcBasicSource).toContain("emit('sensitiveSave', 'Info.Password', 'replace'")
    expect(srcBasicSource).toContain("emit('sensitiveSave', 'Info.Password', 'clear'")
    expect(srcNotifySource).toContain("emit('sensitiveSave', 'Notify.ServerChanKey', 'replace'")
    expect(srcNotifySource).toContain("emit('sensitiveSave', 'Notify.ServerChanKey', 'clear'")
  })

  it('保存 false 作为失败处理且只在成功后重置敏感草稿', () => {
    expect(generalSource).toContain('saved === false')
    expect(generalSource).toContain("throw new Error('用户配置更新未成功')")
    expect(generalSource.indexOf('await updateUserOrThrow(userData)')).toBeLessThan(
      generalSource.indexOf('await loadUserData()', generalSource.indexOf('handleFieldSave'))
    )

    expect(hsrSource).toContain('saved === false')
    expect(hsrSource).toContain('resetSraDraft(key)')
    expect(hsrSource.indexOf('if (saved === false)')).toBeLessThan(
      hsrSource.indexOf('resetSraDraft(key)')
    )

    expect(srcSource).toContain("if (!success) throw new Error('用户配置更新未成功')")
    expect(srcSource.indexOf("if (!success) throw new Error('用户配置更新未成功')")).toBeLessThan(
      srcSource.indexOf('resetPasswordDraft()')
    )
  })

  it('使用紧凑页头、单层磨砂分区、宽容器双栏瀑布流/窄容器单列布局', () => {
    for (const source of [generalSource, hsrSource, srcSource]) {
      expect(source).not.toContain('<a-card class="config-card">')
      expect(source).toContain('class="config-shell"')
      // 宽容器（app-content > 980px）走 CSS multi-column 双栏瀑布流，
      // 卡片各自纵向堆叠、禁止跨列断裂；窄容器回落单列，不再使用等高 grid 行
      expect(source).toContain('@container app-content (min-width: 981px)')
      expect(source).toContain('columns: 2')
      expect(source).toContain('column-gap: var(--v6-space-4)')
      expect(source).toContain('break-inside: avoid')
      expect(source).toContain('column-span: all')
      expect(source).not.toContain('grid-template-columns: repeat(2, minmax(0, 1fr))')
      expect(source).toContain('var(--v6-vibrancy-content)')
      expect(source).toContain("data-perf-mode='low'")
    }
    expect(generalSource).toContain('编辑通用用户')
    expect(hsrSource).toContain('编辑 HSR 用户')
    expect(srcHeaderSource).toContain('编辑 SRC 用户')
    expect(srcHeaderSource).toContain('即时保存')
  })
})
