import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('../index.vue', import.meta.url)), 'utf8')

describe('计划页失败状态契约', () => {
  it('网络错误保留计划页上下文并展示中文可操作提示', () => {
    expect(source).toContain('title="计划列表加载失败"')
    expect(source).toContain('/failed to fetch|networkerror|load failed/i')
    expect(source).toContain('无法连接后端服务，请确认 AUTO-MAS 后端已启动后重试')
    expect(source).toContain('@click="initPlans">重试</a-button>')
  })
})
