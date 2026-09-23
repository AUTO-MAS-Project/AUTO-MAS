import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { hasStoredSecret, isPasswordInput } from './maafwOptionConstraints'

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
