import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/**
 * ScriptConfigMask deterministic 测试集
 *
 * 由于项目未引入 @vue/test-utils，采用与 ScriptCreateDialog.test.ts 一致的源码检视策略：
 * - 验证 v6 token 使用（var(--v6-color-surface-elevated)、var(--v6-radius-card) 等）
 * - 验证 Ant Design 状态映射（a-button type=primary、:loading=saving）
 * - 验证 SRC/MaaEnd 文案映射与 ariaLabel
 * - 验证 visible 守卫与 save 事件触发条件
 * - 验证 prefers-reduced-motion 兼容
 */

const source = readFileSync(new URL('./ScriptConfigMask.vue', import.meta.url), 'utf8')

describe('ScriptConfigMask: v6 token 使用', () => {
  it('背景使用 v6-color-surface-elevated token', () => {
    expect(source).toContain('background: var(--v6-color-surface-elevated)')
  })

  it('圆角使用 v6-radius-card token', () => {
    expect(source).toContain('border-radius: var(--v6-radius-card)')
  })

  it('间距使用 v6-space-6 token', () => {
    expect(source).toContain('padding: var(--v6-space-6)')
  })

  it('阴影使用 v6-shadow-elevated token', () => {
    expect(source).toContain('box-shadow: var(--v6-shadow-elevated)')
  })

  it('边框使用 v6-color-border token', () => {
    expect(source).toContain('border: 1px solid var(--v6-color-border)')
  })

  it('过渡动画使用 v6-motion-fast 与 v6-ease-out token', () => {
    expect(source).toContain('var(--v6-motion-fast, 160ms)')
    expect(source).toContain('var(--v6-ease-out, ease)')
  })

  it('文本色使用 ant-color-text 与 ant-color-text-secondary', () => {
    expect(source).toContain('color: var(--ant-color-text)')
    expect(source).toContain('color: var(--ant-color-text-secondary)')
  })

  it('图标主色使用 ant-color-primary token', () => {
    expect(source).toContain("color: 'var(--ant-color-primary)'")
  })
})

describe('ScriptConfigMask: Ant Design 状态映射', () => {
  it('保存按钮使用 a-button type=primary size=large', () => {
    expect(source).toContain('type="primary"')
    expect(source).toContain('size="large"')
  })

  it('保存按钮 :loading 绑定 saving prop（反映异步保存状态）', () => {
    expect(source).toContain(':loading="saving"')
  })

  it('保存按钮仅在 script 存在时渲染（v-if="script"）', () => {
    expect(source).toContain('v-if="script"')
  })

  it('遮罩层使用 transition 实现淡入淡出', () => {
    expect(source).toContain('name="script-config-mask-fade"')
  })

  it('遮罩层使用 role=dialog 与 aria-modal=true', () => {
    expect(source).toContain('role="dialog"')
    expect(source).toContain('aria-modal="true"')
  })
})

describe('ScriptConfigMask: SRC/MaaEnd 文案映射', () => {
  it('SRC 标题为"正在进行SRC配置"', () => {
    expect(source).toContain("title: '正在进行SRC配置'")
  })

  it('MaaEnd 标题为"正在进行 MaaEnd 配置"', () => {
    expect(source).toContain("title: '正在进行 MaaEnd 配置'")
  })

  it('SRC 文案首行说明 SRC 脚本配置', () => {
    expect(source).toContain('当前正在配置SRC脚本，请在SRC配置界面完成相关设置。')
  })

  it('MaaEnd 文案首行说明 MaaEnd 脚本配置', () => {
    expect(source).toContain('当前正在配置 MaaEnd 脚本，请在 MaaEnd 配置界面完成相关设置。')
  })

  it('SRC ariaLabel 为"SRC 配置遮罩层"', () => {
    expect(source).toContain("ariaLabel: 'SRC 配置遮罩层'")
  })

  it('MaaEnd ariaLabel 为"MaaEnd 配置遮罩层"', () => {
    expect(source).toContain("ariaLabel: 'MaaEnd 配置遮罩层'")
  })

  it('kind 缺失时回退到默认 ariaLabel"脚本配置遮罩层"', () => {
    expect(source).toContain("?? '脚本配置遮罩层'")
  })
})

describe('ScriptConfigMask: visible 守卫与 save 事件', () => {
  it('根元素使用 v-if="visible" 控制显隐', () => {
    expect(source).toContain('v-if="visible"')
  })

  it('点击保存按钮触发 save 事件并携带 script', () => {
    expect(source).toContain('@click="emit(\'save\', script)"')
  })

  it('save emit 类型签名为 (script: Script)', () => {
    expect(source).toMatch(/event:\s*['"]save['"]\s*,\s*script:\s*Script/)
  })

  it('Props 包含 visible、script、kind、saving 四个字段', () => {
    expect(source).toContain('visible: boolean')
    expect(source).toContain('script: Script | null')
    expect(source).toContain('kind: ScriptConfigSessionKind | null')
    expect(source).toContain('saving?: boolean')
  })

  it('saving 默认值为 false', () => {
    expect(source).toMatch(/saving:\s*false/)
  })
})

describe('ScriptConfigMask: 可访问性与 reduced-motion', () => {
  it('支持 prefers-reduced-motion: reduce 时禁用过渡动画', () => {
    expect(source).toContain('@media (prefers-reduced-motion: reduce)')
    expect(source).toMatch(/transition:\s*none/)
  })

  it('遮罩层使用 position: fixed 覆盖全屏', () => {
    expect(source).toContain('position: fixed')
    expect(source).toContain('top: 0')
    expect(source).toContain('left: 0')
    expect(source).toContain('right: 0')
    expect(source).toContain('bottom: 0')
  })

  it('遮罩层 z-index=9999 确保高于其他模态', () => {
    expect(source).toContain('z-index: 9999')
  })

  it('背景使用 color-mix 半透明黑色实现遮罩', () => {
    expect(source).toContain('color-mix(in srgb, #000 45%, transparent)')
  })
})

describe('ScriptConfigMask: 文案与按钮状态交互', () => {
  it('描述文案包含两行（br 标签分隔）', () => {
    expect(source).toContain('<br />')
  })

  it('保存按钮文案为"保存配置"', () => {
    expect(source).toContain('保存配置')
  })

  it('第二行文案明确提示"解除页面锁定"', () => {
    expect(source).toContain('解除页面锁定')
  })

  it('使用 SettingOutlined 图标作为遮罩主图标', () => {
    expect(source).toContain('SettingOutlined')
    expect(source).toContain("fontSize: '48px'")
  })
})
