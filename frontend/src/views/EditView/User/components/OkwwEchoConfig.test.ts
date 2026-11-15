import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import Antd from 'ant-design-vue'
import OkwwEchoConfig from './OkwwEchoConfig.vue'

async function render(config: Record<string, string | number | boolean>, disabled = false) {
  const app = createSSRApp({
    render: () =>
      h(OkwwEchoConfig, {
        modelValue: config,
        disabled,
        overlayEnabled: true,
      }),
  })
  app.use(Antd)
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  return renderToString(app)
}
describe('4C Echo configuration', () => {
  it('inherits without showing editable farming fields until enabled', async () => {
    const html = await render({})
    expect(html).toContain('okwwEchoInherit')
    expect(html).not.toContain('Repeat Farm Count')
  })
  it('shows the selected destination index and saved count', async () => {
    const html = await render({ 'Teleport to Boss': 'Boss Challenge', 'Repeat Farm Count': 5 })
    expect(html).toContain('Which Boss Challenge to Teleport')
    expect(html).not.toContain('Which Weekly Boss to Teleport')
    expect(html).toContain('value="5"')
    expect(html).not.toContain('NaN')
  })
  it('locks editing and native configuration together', async () => {
    const html = await render({ 'Teleport to Boss': 'Weekly Challenge' }, true)
    expect(html).toMatch(/<input[^>]*disabled/)
    expect(html).toMatch(/<button[^>]*disabled/)
  })
})
