import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const viewDir = new URL('../', import.meta.url)
const pluginDir = new URL('./', import.meta.url)

const pluginViewSource = readFileSync(fileURLToPath(new URL('./Plugin.vue', viewDir)), 'utf8')
const dataSource = readFileSync(
  fileURLToPath(new URL('./composables/usePluginData.ts', pluginDir)),
  'utf8'
)
const listSource = readFileSync(
  fileURLToPath(new URL('./components/PluginInstanceList.vue', pluginDir)),
  'utf8'
)
const detailSource = readFileSync(
  fileURLToPath(new URL('./components/PluginInstanceDetail.vue', pluginDir)),
  'utf8'
)
const pageHostSource = readFileSync(fileURLToPath(new URL('./PluginPageHost.vue', viewDir)), 'utf8')
const schemaFormSource = readFileSync(
  fileURLToPath(new URL('../components/SchemaForm.vue', viewDir)),
  'utf8'
)
const elementHostSource = readFileSync(
  fileURLToPath(new URL('./PluginElementHost.vue', viewDir)),
  'utf8'
)

describe('Plugin management fidelity contract', () => {
  it('uses the macOS shell and a frameless split workspace', () => {
    expect(pluginViewSource).toContain("from '@/components/mac/PageHeader.vue'")
    expect(pluginViewSource).toContain("from '@/components/mac/Toolbar.vue'")
    expect(pluginViewSource).toContain('<PageHeader')
    expect(pluginViewSource).toContain('<Toolbar')
    expect(pluginViewSource).toContain('class="plugin-workspace"')
    // 双 pane 分栏结构保留
    expect(pluginViewSource).toMatch(/\.plugin-workspace\s*\{[^}]*grid-template-columns:/s)
    // 拒绝嵌套大框：workspace 不再是 border+shadow+毛玻璃的大卡片，内容直接铺在窗体背景上
    expect(pluginViewSource).not.toMatch(
      /\.plugin-workspace\s*\{[^}]*(?:border:|box-shadow:|backdrop-filter:)/s
    )
    // 双 pane 之间仍保留分隔线
    expect(pluginViewSource).toMatch(/\.plugin-list-pane\s*\{[^}]*border-right:/s)
    expect(pluginViewSource).not.toContain('<a-row')
    expect(pluginViewSource).not.toContain('<a-col')
    expect(listSource).not.toContain('<a-card')
    expect(detailSource).not.toContain('class="section-card detail-card"')
  })

  it('renders plugin config as an iPad-settings style masonry inside plugin-page', () => {
    // 详情卡内 SchemaForm 使用 plugin-grid 布局
    expect(detailSource).toContain('layout="plugin-grid"')
    // plugin-page 容器内以 multi-column 瀑布取代 12 列等高行网格（恒真查询表达"在插件页内"）
    expect(schemaFormSource).toMatch(
      /@container plugin-page \(min-width: 0px\)\s*\{[\s\S]*?\.schema-form-grid\s*\{[^}]*columns: 1/
    )
    // 卡片防跨列断裂：inline-block + width:100% + break-inside:avoid
    expect(schemaFormSource).toMatch(
      /@container plugin-page \(min-width: 0px\)\s*\{[\s\S]*?\.schema-form-grid \.schema-item\s*\{[^}]*break-inside: avoid/
    )
    // 宽容器(>980px)切双栏
    expect(schemaFormSource).toMatch(
      /@container plugin-page \(min-width: 981px\)\s*\{\s*\.schema-form-grid\s*\{[^}]*columns: 2/
    )
    // 列内卡片间距使用现有 spacing token
    expect(schemaFormSource).toContain('margin-bottom: var(--v6-space-3, 12px)')
    // 基础 12 列网格仍保留给其他 SchemaForm 使用方（EditView 等）
    expect(schemaFormSource).toContain('grid-template-columns: repeat(12, minmax(0, 1fr))')
  })

  it('preserves every instance, package and reload operation', () => {
    const operations = [
      ['plugins.get', '/api/plugins/get'],
      ['plugins.add', '/api/plugins/add'],
      ['plugins.update', '/api/plugins/update'],
      ['plugins.delete', '/api/plugins/delete'],
      ['plugins.reload', '/api/plugins/reload'],
      ['plugins.reload_instance', '/api/plugins/reload_instance'],
      ['plugins.reload_plugin', '/api/plugins/reload_plugin'],
      ['plugins.uninstall_package', '/api/plugins/uninstall_package'],
    ] as const

    for (const [endpoint, path] of operations) {
      expect(dataSource).toContain(`'${endpoint}'`)
      expect(dataSource).toContain(`'${path}'`)
    }

    for (const eventName of [
      'submit-edit',
      'reset-edit',
      'open-json-preview',
      'reload-instance',
      'reload-plugin',
      'uninstall-plugin',
      'delete-instance',
      'trigger-action',
      'trigger-schema-action',
      'copy-diagnostics',
    ]) {
      expect(pluginViewSource).toContain(`@${eventName}=`)
    }

    expect(listSource).toContain('@update:checked=')
    expect(listSource).toContain('@end=')
    expect(pluginViewSource).toContain('pluginLayout.syncWithInstances')
  })

  it('keeps schema validation, sensitive-field merge and realtime state updates', () => {
    expect(pluginViewSource).toContain('collectSchemaFieldErrors')
    expect(pluginViewSource).toContain('validateActiveSchemaBeforeSubmit')
    expect(pluginViewSource).toContain('mergeConfigPatch')
    expect(pluginViewSource).toContain('sanitizeErrorForLog')
    expect(detailSource).toContain('buildSavePayload')
    expect(detailSource).toContain('validateSchema')
    expect(detailSource).toContain('@sensitive-dirty-change=')
    expect(dataSource).toContain("payload.kind === 'snapshot'")
    expect(dataSource).toContain("payload.kind === 'runtime_state'")
    expect(dataSource).toContain("payload.kind === 'hmr'")
    expect(dataSource).toContain("type: 'response', id: 'Client'")
  })

  it('does not present a refresh-only drop target as package installation', () => {
    expect(pluginViewSource).toContain("router.push('/plugins-market')")
    expect(pluginViewSource).toContain('showItemInFolder(pluginPath)')
    expect(pluginViewSource).not.toContain('handleInstallFiles')
    expect(pluginViewSource).not.toContain('electronAPI as any)?.openPath')
    expect(listSource).toContain('从插件市场获取插件')
    expect(listSource).not.toContain('拖拽插件包到此处安装')
    expect(listSource).not.toContain('支持 .plugin / .zip / .maafw')
  })

  it('keeps plugin page isolation, URL validation and page-change reload behavior', () => {
    expect(pageHostSource).toContain('validatePluginIframeUrl')
    expect(pageHostSource).toContain(
      "const IFRAME_SANDBOX = 'allow-scripts allow-forms allow-popups allow-modals allow-downloads'"
    )
    expect(pageHostSource).toContain('() => [props.page.id, props.page.url] as const')
    expect(pageHostSource).toContain('<PluginErrorBoundary')

    expect(elementHostSource).toContain('validatePluginEntryUrl')
    expect(elementHostSource).toContain('isManifestVersionSupported')
    expect(elementHostSource).toContain('<PluginErrorBoundary')
    expect(elementHostSource).toContain('releasePage?.()')
  })
})
