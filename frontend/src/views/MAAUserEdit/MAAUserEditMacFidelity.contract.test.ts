import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const moduleDir = dirname(fileURLToPath(import.meta.url))
const userEditDir = resolve(moduleDir, '../EditView/User')
const readModule = (name: string) => readFileSync(resolve(moduleDir, name), 'utf8')

describe('MAA 用户编辑功能保真与 macOS UI 契约', () => {
  const pageSource = readFileSync(resolve(userEditDir, 'MAAUserEdit.vue'), 'utf8')
  const headerSource = readModule('MAAUserEditHeader.vue')
  const basicSource = readModule('BasicInfoSection.vue')
  const stageSource = readModule('StageConfigSection.vue')
  const taskSource = readModule('TaskConfigSection.vue')
  const skylandSource = readModule('SkylandConfigSection.vue')
  const notifySource = readModule('NotifyConfigSection.vue')

  it('保留 MAA 用户编辑的关卡、任务、通知、外部配置和即时保存入口', () => {
    expect(pageSource).toContain('<StageConfigSection')
    expect(pageSource).toContain('<TaskConfigSection')
    expect(pageSource).toContain('<NotifyConfigSection')
    expect(pageSource).toContain('handleMAAConfig')
    expect(pageSource).toContain('handleSaveMAAConfig')
    expect(pageSource).toContain('handleFieldSave')
    expect(stageSource).toContain("emit('save'")
    expect(taskSource).toContain("emit('save'")
    expect(notifySource).toContain('<WebhookManager')
  })

  it('敏感字段不回填到输入控件，必须明确替换或清空', () => {
    expect(basicSource).toContain(':value="passwordDraft"')
    expect(basicSource).not.toContain('v-model:value="formData.Info.Password"')
    expect(basicSource).toContain('保存新值')
    expect(basicSource).toContain('清空原值')

    expect(skylandSource).toContain(':value="tokenDraft"')
    expect(skylandSource).not.toContain('v-model:value="formData.Info.SklandToken"')
    expect(notifySource).toContain(':value="serverChanKeyDraft"')
    expect(notifySource).not.toContain('v-model:value="formData.Notify.ServerChanKey"')

    expect(pageSource).toContain('handleSensitiveSave')
    expect(pageSource).toContain("intent === 'clear' ? ''")
    expect(pageSource).toContain('updateUserOrThrow')
    expect(pageSource).toContain('saved === false')
  })

  it('使用紧凑页头、单层磨砂表单和宽容器双栏瀑布流布局', () => {
    expect(headerSource).toContain('编辑 MAA 用户')
    expect(headerSource).toContain('即时保存')
    expect(pageSource).not.toContain('<a-card class="config-card">')
    expect(pageSource).toContain('class="config-shell"')
    // 宽容器（app-content > 980px）走 CSS multi-column 双栏瀑布流，
    // 卡片各自纵向堆叠、禁止跨列断裂；窄容器回落单列，不再使用等高 grid 行
    expect(pageSource).toContain('@container app-content (min-width: 981px)')
    expect(pageSource).toContain('columns: 2')
    expect(pageSource).toContain('column-gap: var(--v6-space-4)')
    expect(pageSource).toContain('break-inside: avoid')
    expect(pageSource).toContain('column-span: all')
    expect(pageSource).not.toContain('grid-template-columns: repeat(2, minmax(0, 1fr))')
    expect(pageSource).toContain('var(--v6-vibrancy-content)')
    expect(pageSource).toContain("data-perf-mode='low'")
    expect(pageSource).toContain('prefers-reduced-motion')
  })
})
