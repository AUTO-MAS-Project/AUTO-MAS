import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// 锁定配置弹窗层级方案：z-index 900 压在标题栏之下 + 嵌套浮层挂 wrap 容器。
// 这些约束没有运行时断言点，只能用源码文本锁（照 ScriptCreateDialog.test.ts）。
const source = readFileSync(
  new URL('./components/NotifyChannelModal.vue', import.meta.url),
  'utf8'
)
const tabSource = readFileSync(new URL('./TabNotify.vue', import.meta.url), 'utf8')
const clawSource = readFileSync(
  new URL('./components/ClawBinding.vue', import.meta.url),
  'utf8'
)

describe('通知配置弹窗层级方案', () => {
  it('弹窗连同遮罩整体压在标题栏（1000）之下', () => {
    expect(source).toContain(':z-index="900"')
    expect(tabSource).toContain("'.notify-channel-modal'")
  })

  it('换渠道重置内容、弹窗常驻不销毁', () => {
    expect(source).toContain('wrap-class-name="notify-channel-modal"')
    expect(source).toContain(':key="channel.key"')
    expect(source).not.toContain('destroy-on-close')
    expect(source).not.toContain('destroyOnClose')
  })
})

describe('通知页编辑提交与 Claw 单实例', () => {
  it('关闭与切换都以提交未失焦编辑为第一步', () => {
    expect(tabSource).toContain('commitFocus')
    expect(tabSource).toMatch(/const closeModal = \(\) => \{\s*commitFocus\(\)/)
    expect(tabSource).toMatch(/const openChannel = \(key: string\) => \{\s*commitFocus\(\)/)
  })

  it('只有 TabNotify 调用 useClawBinding，ClawBinding 只接收提升后的状态', () => {
    expect(tabSource).toContain("useClawBinding('weixin'")
    expect(tabSource).toContain("useClawBinding('qq'")
    expect(clawSource).not.toMatch(/[^e]useClawBinding\(/)
    expect(clawSource).toContain('binding: ClawBindingState')
  })
})
