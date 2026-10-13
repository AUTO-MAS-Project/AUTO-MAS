import { describe, expect, it } from 'vitest'
import type { MaaFWOptionInputInfo } from '@/types/script'
import { checkMaaFWInputValue, effectiveMaaFWInputFieldValue } from './maafwOptionValues'

const fiveDigits: MaaFWOptionInputInfo = { name: 'code', default: '10001', verify: '^\\d{5}$' }
const integer: MaaFWOptionInputInfo = { name: 'count', pipelineType: 'int', default: '260' }
const integerNoDefault: MaaFWOptionInputInfo = { name: 'count', pipelineType: 'int' }

describe('checkMaaFWInputValue', () => {
  it('字符串字段只有空串算没填，不过 verify', () => {
    expect(checkMaaFWInputValue(fiveDigits, '')).toBeNull()
  })

  it('字符串字段的纯空白是填了的值，照常过 verify', () => {
    expect(checkMaaFWInputValue(fiveDigits, '   ')).toBe('verify')
    expect(checkMaaFWInputValue({ name: 'note' }, '   ')).toBeNull()
  })

  it('合规 / 不合规的字符串', () => {
    expect(checkMaaFWInputValue(fiveDigits, '12345')).toBeNull()
    expect(checkMaaFWInputValue(fiveDigits, '1234')).toBe('verify')
    expect(checkMaaFWInputValue({ name: 'x', verify: '(' }, 'a')).toBe('patternInvalid')
  })

  it('数字字段去掉空白后为空才算没填，有 default 才能留空', () => {
    expect(checkMaaFWInputValue(integer, '  ')).toBeNull()
    expect(checkMaaFWInputValue(integerNoDefault, '  ')).toBe('wholeNumber')
    expect(checkMaaFWInputValue(integer, ' 12 ')).toBeNull()
    expect(checkMaaFWInputValue(integer, '1.5')).toBe('wholeNumber')
    expect(checkMaaFWInputValue({ name: 'r', pipelineType: 'float' }, 'abc')).toBe('number')
  })
})

describe('effectiveMaaFWInputFieldValue', () => {
  it('字符串字段空串或没存时显示 default，纯空白原样显示', () => {
    expect(effectiveMaaFWInputFieldValue(fiveDigits, undefined)).toBe('10001')
    expect(effectiveMaaFWInputFieldValue(fiveDigits, { code: '' })).toBe('10001')
    expect(effectiveMaaFWInputFieldValue(fiveDigits, { code: '   ' })).toBe('   ')
  })

  it('密码字段不回落', () => {
    expect(effectiveMaaFWInputFieldValue({ name: 'pw', password: true, default: 'x' }, {})).toBe('')
  })
})
