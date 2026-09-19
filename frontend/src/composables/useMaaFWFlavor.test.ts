import { readFileSync } from 'node:fs'
import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { resolveMaaFWFlavor, useMaaFWFlavor } from './useMaaFWFlavor'
import zhCN from '@/i18n/locales/zh-CN'
import { MAS_DOC_URLS } from '@/utils/openExternal'

const lookup = (key: string): unknown =>
  key.split('.').reduce<unknown>((node, part) => {
    return node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined
  }, zhCN)

describe('MaaFW flavor 文案表', () => {
  it('M9A 取特调表，其余类型都落到通用 MaaFW', () => {
    expect(resolveMaaFWFlavor('M9A').type).toBe('M9A')
    for (const type of ['MaaFW', 'MAA', 'General', '', null, undefined]) {
      expect(resolveMaaFWFlavor(type).type).toBe('MaaFW')
    }
  })

  it('M9A 的每一处差异都落在文案与身份上，没有行为开关', () => {
    const m9a = resolveMaaFWFlavor('M9A')
    const maafw = resolveMaaFWFlavor('MaaFW')
    expect(m9a.docUrl).toBe(MAS_DOC_URLS.scriptTypes.M9A)
    expect(maafw.docUrl).toBe(MAS_DOC_URLS.scripts)
    expect(m9a.scriptTitleKey).toBe('edit.m9aFlavorScriptTitle')
    expect(maafw.scriptTitleKey).toBeNull()
    expect(m9a.queueHintKey).toBe('edit.m9aFlavorQueueHint')
    expect(maafw.queueHintKey).toBeNull()
    // 两张表的字段集完全一致：组件只按同一组字段取值，没有任何 flavor 独有的键
    expect(Object.keys(m9a).sort()).toEqual(Object.keys(maafw).sort())
    for (const value of Object.values(m9a)) expect(typeof value === 'boolean').toBe(false)
  })

  it('表里引用的每个 i18n key 在中文词表里都存在（中文是源语言）', () => {
    for (const flavor of [resolveMaaFWFlavor('M9A'), resolveMaaFWFlavor('MaaFW')]) {
      for (const [field, value] of Object.entries(flavor)) {
        if (!field.endsWith('Key') || value === null) continue
        expect([field, value, typeof lookup(value as string)]).toEqual([field, value, 'string'])
      }
    }
  })

  it('M9A 文案说清了账号绑定与自动加入的首尾任务', () => {
    const m9a = resolveMaaFWFlavor('M9A')
    expect(lookup(m9a.accountPlaceholderKey)).toContain('切换账号')
    expect(lookup(m9a.queueHintKey!)).toContain('无需手动添加')
    expect(lookup(m9a.sourcePlaceholderKey)).toContain('interface.json')
    // 密码字段不跟着 flavor 走，两种 flavor 都是「仅本地记录」
    expect(lookup('edit.localNoteOnly')).toContain('本地记录')
  })

  it('响应式版本跟着脚本类型变（导入后后端会原地换类型）', () => {
    const type = ref<string>('MaaFW')
    const flavor = useMaaFWFlavor(type)
    expect(flavor.value.type).toBe('MaaFW')
    type.value = 'M9A'
    expect(flavor.value.type).toBe('M9A')
  })

  it('MaaFW 脚本页与用户页都按脚本当前类型取 flavor，不读路由 meta', () => {
    const scriptPage = readFileSync(
      new URL('../views/EditView/Script/MaaFWScriptEdit.vue', import.meta.url),
      'utf8'
    )
    const userPage = readFileSync(
      new URL('../views/EditView/User/MaaFWUserEdit.vue', import.meta.url),
      'utf8'
    )
    for (const source of [scriptPage, userPage]) {
      expect(source).toContain('useMaaFWFlavor(')
      expect(source).not.toContain('route.meta.scriptType')
    }
    // 导入 / 重新导入成功后要重新拉脚本类型：后端按项目内容原地换类型
    expect(scriptPage).toContain('refreshScriptType')
  })
})
