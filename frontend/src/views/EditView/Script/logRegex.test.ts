import { describe, expect, it } from 'vitest'

import { toJsRegexSource, validateRegexPattern } from './logRegex'

describe('validateRegexPattern', () => {
  it('留空视为未配置，不报错', () => {
    expect(validateRegexPattern('')).toBeNull()
    expect(validateRegexPattern('   ')).toBeNull()
  })

  it('合法正则通过校验', () => {
    expect(validateRegexPattern(String.raw`任务\d+ 执行完成`)).toBeNull()
    expect(validateRegexPattern('成功|完成')).toBeNull()
  })

  it('非法正则返回错误信息', () => {
    expect(validateRegexPattern('[unclosed')).not.toBeNull()
    expect(validateRegexPattern('a{2,1}')).not.toBeNull()
  })

  it('Python 具名分组不被误报为错误', () => {
    expect(validateRegexPattern(String.raw`(?P<task>\w+) 执行完成`)).toBeNull()
    expect(validateRegexPattern(String.raw`(?P<t>\w+)-(?P=t)`)).toBeNull()
  })
})

describe('toJsRegexSource', () => {
  it('归一 Python 具名分组与反向引用', () => {
    expect(toJsRegexSource(String.raw`(?P<t>\w+)-(?P=t)`)).toBe(String.raw`(?<t>\w+)-\k<t>`)
  })

  it('不改写普通正则', () => {
    expect(toJsRegexSource(String.raw`任务\d+`)).toBe(String.raw`任务\d+`)
  })
})
