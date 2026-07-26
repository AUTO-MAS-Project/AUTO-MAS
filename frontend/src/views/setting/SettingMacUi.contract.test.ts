import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const settingDir = new URL('./', import.meta.url)
const indexSource = readFileSync(fileURLToPath(new URL('./index.vue', settingDir)), 'utf8')
const headerSource = readFileSync(
  fileURLToPath(new URL('./SettingTabHeader.vue', settingDir)),
  'utf8'
)

const tabFiles = [
  'TabBasic.vue',
  'TabFunction.vue',
  'TabNotify.vue',
  'TabAdvanced.vue',
  'TabOthers.vue',
] as const

const tabSources = Object.fromEntries(
  tabFiles.map(file => [
    file,
    readFileSync(fileURLToPath(new URL(`./${file}`, settingDir)), 'utf8'),
  ])
)

describe('Setting macOS UI contract', () => {
  it('uses a macOS Ventura/Sonoma sidebar with colored rounded-square icons', () => {
    // 主体：左侧边栏 + 右侧内容区
    expect(indexSource).toContain('class="settings-body"')
    expect(indexSource).toContain('<aside class="settings-sidebar"')
    expect(indexSource).toContain('<main class="settings-content"')
    // iOS 风格彩色图标侧边栏
    expect(indexSource).toContain('class="settings-nav"')
    expect(indexSource).toContain('role="tablist"')
    expect(indexSource).toContain('role="tab"')
    expect(indexSource).toContain('nav-icon-appearance')
    expect(indexSource).toContain('nav-icon-features')
    expect(indexSource).toContain('nav-icon-notifications')
    expect(indexSource).toContain('nav-icon-logs')
    expect(indexSource).toContain('nav-icon-about')
    expect(indexSource).toContain('nav-selected')
    expect(indexSource).toContain('class="nav-icon-wrap" :class="`nav-icon-${item.iconKind}`"')
    expect(indexSource).not.toContain('[`nav-icon-${item.iconKind}`]: true')
    // 右侧面板标题（精简，不与 PageHeader 重复）
    expect(indexSource).toContain('class="settings-panel-header"')
    expect(indexSource).toContain('class="settings-panel-title"')
    expect(indexSource).toContain('class="settings-panel-subtitle"')
    // 不再使用旧的 a-segmented / a-tabs / a-tab-pane
    expect(indexSource).not.toContain('<a-segmented')
    expect(indexSource).not.toContain('<a-tabs')
    expect(indexSource).not.toContain('<a-tab-pane')
    expect(indexSource).not.toContain('title="偏好设置"')
    expect(indexSource).not.toContain('class="settings-section"')
  })

  it('renders a single panel header without per-tab duplicate titles', () => {
    // SettingTabHeader 不再渲染 h3 大标题，只承载说明/操作/告警
    expect(headerSource).not.toContain('<h3')
    expect(headerSource).toContain('setting-tab-summary')
    // 各 Tab 也不通过 SettingTabHeader 传入 title 属性
    for (const source of Object.values(tabSources)) {
      expect(source).not.toMatch(/<SettingTabHeader[^>]*\btitle=/)
    }
  })

  it('keeps the compact frosted NSBox container without heavy title rails or dividers', () => {
    // NSBox 分组容器：12px 圆角、0.5px 边框、毛玻璃，使用 v6 token
    // 注意：选择器在源码中是 :deep(.form-section) { ... }，需要兼容 :deep() 包裹
    expect(indexSource).toMatch(
      /form-section\)?\s*\{[^}]*backdrop-filter:\s*var\(--v6-backdrop-vibrancy\)/s
    )
    expect(indexSource).toMatch(
      /form-section\)?\s*\{[^}]*border-radius:\s*var\(--v6-radius-card\)/s
    )
    expect(indexSource).toMatch(/form-section\)?\s*\{[^}]*border:\s*0\.5px/s)
    // 侧边栏使用毛玻璃 vibrancy 与 0.5px 边框
    expect(indexSource).toMatch(
      /\.settings-sidebar\s*\{[^}]*backdrop-filter:\s*var\(--v6-backdrop-vibrancy\)/s
    )
    expect(indexSource).toMatch(/\.settings-sidebar\s*\{[^}]*border-right:\s*0\.5px/s)
    // 不使用粗分隔线（2px border-bottom）或 ::before 装饰条
    expect(indexSource).not.toContain('.section-header h3::before')
    expect(indexSource).not.toMatch(/border-bottom:\s*2px/)
    expect(headerSource).not.toMatch(/border-bottom:\s*2px/)
    // 表单行之间使用 0.5px 分隔线
    expect(indexSource).toMatch(/row-separator\)?\s*\{[^}]*height:\s*0\.5px/s)
  })

  it('preserves every HEAD-era settings persistence entry point', () => {
    const expectedBindings: Record<string, string[]> = {
      'TabBasic.vue': ['UI.IfShowTray', 'UI.IfToTray', 'UI.IfHideCloseButton'],
      'TabFunction.vue': [
        'Start.IfSelfStart',
        'Start.IfMinimizeDirectly',
        'Function.HistoryRetentionTime',
        'Function.IfSilence',
        'Function.IfAllowSleep',
        'Function.IfAgreeBilibili',
        'Function.IfBlockAd',
        'Voice.Enabled',
        'Voice.Type',
      ],
      'TabNotify.vue': [
        'Notify.SendTaskResultTime',
        'Notify.IfSendStatistic',
        'Notify.IfSendSixStar',
        'Notify.IfPushPlyer',
        'Notify.IfSendMail',
        'Notify.SMTPServerAddress',
        'Notify.FromAddress',
        'Notify.AuthorizationCode',
        'Notify.ToAddress',
        'Notify.IfServerChan',
        'Notify.ServerChanKey',
        'Notify.IfKoishiSupport',
        'Notify.KoishiServerAddress',
        'Notify.KoishiToken',
      ],
      'TabOthers.vue': [
        'Update.IfAutoUpdate',
        'Update.Source',
        'Update.Channel',
        'Update.ProxyAddress',
        'Update.MirrorChyanCDK',
        'Update.GitHubToken',
      ],
    }

    for (const [file, bindings] of Object.entries(expectedBindings)) {
      const source = tabSources[file]
      for (const binding of bindings) {
        const [category, key] = binding.split('.')
        expect(source).toContain(`handleSettingChange('${category}', '${key}'`)
      }
    }

    expect(tabSources['TabNotify.vue']).toContain('<a-input-password')
    expect(tabSources['TabNotify.vue']).toContain("'AuthorizationCode'")
    expect(tabSources['TabNotify.vue']).toContain("'ServerChanKey'")
    expect(tabSources['TabNotify.vue']).toContain("'KoishiToken'")
    expect(tabSources['TabOthers.vue']).toContain("'MirrorChyanCDK'")
    expect(tabSources['TabOthers.vue']).toContain("'GitHubToken'")
  })

  it('keeps non-field interactions wired', () => {
    expect(indexSource).toContain('testNotifyApiSettingTestNotifyPost')
    expect(indexSource).toContain('globalCheckUpdate(false, true)')
    expect(tabSources['TabAdvanced.vue']).toContain('@click="exportLogsZip"')
    expect(tabSources['TabAdvanced.vue']).toContain('@click="openDevTools"')
    expect(tabSources['TabNotify.vue']).toContain('<WebhookManager')
    expect(tabSources['TabNotify.vue']).toContain('@click="testNotify"')
    expect(tabSources['TabFunction.vue']).toContain('@click="handleExternalLink"')
    expect(tabSources['TabOthers.vue']).toContain('@click="checkUpdate"')
  })

  it('lays out setting cards as a 3/2/1-column waterfall driven by container width', () => {
    // 基准双列瀑布：卡片列内独立堆叠，不做行等高
    expect(indexSource).toContain('columns: 2;')
    expect(indexSource).toContain('break-inside: avoid;')
    // 超宽容器升三列、窄容器降单列，均按 settings-content 真实可用宽度切档
    expect(indexSource).toContain('@container settings-content (min-width: 1400px)')
    expect(indexSource).toContain('columns: 3;')
    expect(indexSource).toContain('@container settings-content (max-width: 980px)')
    expect(indexSource).toContain('columns: 1;')
  })
})
