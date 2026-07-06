import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./QuickNavPage.vue', import.meta.url), 'utf8')

describe('QuickNavPage feedback', () => {
  it('uses Ant Design Vue for destructive confirmation and feedback', () => {
    expect(source).toContain('Modal.confirm({')
    expect(source).toContain("message.success('本地存储已清除，建议刷新页面')")
    expect(source).not.toMatch(/(^|[^\w.])confirm\(/m)
    expect(source).not.toMatch(/(^|[^\w.])alert\(/m)
  })
})
