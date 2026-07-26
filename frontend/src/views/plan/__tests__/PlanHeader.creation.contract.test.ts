import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('../components/PlanHeader.vue', import.meta.url)),
  'utf8'
)

describe('PlanHeader 创建计划交互契约', () => {
  it('主按钮只打开类型对话框，不直接创建计划', () => {
    expect(source).toContain('<a-dropdown-button')
    expect(source).toContain('@click="openCreateDialog"')
    expect(source).toContain('createDialogOpen.value = true')
    expect(source).not.toContain('@click="handleAddPlan"')
  })

  it('下拉箭头只交给 dropdown 展开，选择菜单项后仍进入确认流程', () => {
    expect(source).toContain('<template #overlay>')
    expect(source).toContain('@click="handlePlanTypeMenuClick"')
    expect(source).toContain('selectedPlanType.value = key')
    expect(source).toContain('openCreateDialog()')
  })

  it('只有确认对话框后才触发 add-plan', () => {
    expect(source).toContain('@ok="confirmCreate"')
    expect(source).toContain("emit('add-plan', selectedPlanType.value)")
  })
})
