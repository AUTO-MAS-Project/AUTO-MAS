import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { MaaFWOptionInfo } from '@/types/script'
import {
  getCheckboxCountState,
  hasStoredSecret,
  isCheckboxCaseLocked,
  isPasswordInput,
} from './maafwOptionConstraints'

const checkbox = (minCount: number | null, maxCount: number | null): MaaFWOptionInfo => ({
  name: 'cb',
  type: 'checkbox',
  controller: [],
  resource: [],
  cases: ['a', 'b', 'c'].map(name => ({ name, option: [] })),
  inputs: [],
  hotkeys: [],
  minCount,
  maxCount,
})

describe('checkbox min_count / max_count', () => {
  it('没有限制时不给状态', () => {
    expect(getCheckboxCountState(checkbox(null, null), ['a'])).toBeNull()
  })

  it('按 case 去重计数并判断少选 / 多选', () => {
    const option = checkbox(1, 2)
    expect(getCheckboxCountState(option, [])).toMatchObject({ count: 0, violation: 'min' })
    expect(getCheckboxCountState(option, ['a', 'a', 'x'])).toMatchObject({
      count: 1,
      violation: null,
    })
    expect(getCheckboxCountState(option, ['a', 'b', 'c'])).toMatchObject({
      count: 3,
      violation: 'max',
    })
  })

  it('达到上限后只锁没勾的，已勾的还能取消', () => {
    const option = checkbox(1, 2)
    expect(isCheckboxCaseLocked(option, ['a'], 'b')).toBe(false)
    expect(isCheckboxCaseLocked(option, ['a', 'b'], 'c')).toBe(true)
    expect(isCheckboxCaseLocked(option, ['a', 'b'], 'a')).toBe(false)
    expect(isCheckboxCaseLocked(checkbox(1, null), ['a', 'b'], 'c')).toBe(false)
  })
})

describe('password 输入', () => {
  it('只认 password === true', () => {
    expect(isPasswordInput({ name: 'pw', password: true })).toBe(true)
    expect(isPasswordInput({ name: 'pw' })).toBe(false)
    expect(hasStoredSecret('mas-dpapi:xxx')).toBe(true)
    expect(hasStoredSecret('')).toBe(false)
  })

  it('编辑器用掩码框、不把已保存的值绑进输入框', () => {
    const source = readFileSync(new URL('./MaaFWTaskOptionEditor.vue', import.meta.url), 'utf8')
    const passwordBlock = source.slice(
      source.indexOf('v-if="isPasswordInput(inputItem)"'),
      source.indexOf('v-else-if="isIntegerInput(inputItem)"')
    )
    expect(passwordBlock).toContain('<a-input-password')
    expect(passwordBlock).toContain(':value="getPasswordDraft(option.name, inputItem.name)"')
    expect(passwordBlock).not.toContain(':value="getInputFieldValue')
  })
})
