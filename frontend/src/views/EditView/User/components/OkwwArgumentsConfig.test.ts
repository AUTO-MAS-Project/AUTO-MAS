import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import Antd, { Form } from 'ant-design-vue'
import OkwwArgumentsConfig from './OkwwArgumentsConfig.vue'
import { getDefaultOkwwTaskConfig } from './okwwTaskConfig'

async function renderArguments(custom: boolean, disabled = false) {
  const task = getDefaultOkwwTaskConfig()
  task.IfCustomArguments = custom
  task.CustomArguments = '-t OtherTask -h'
  const app = createSSRApp({
    render: () =>
      h(Form, { disabled }, () =>
        h(OkwwArgumentsConfig, { modelValue: task, scriptId: 'test', save: async () => true })
      ),
  })
  app.use(Antd)
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  return renderToString(app)
}

describe('OK-WW custom arguments', () => {
  it('keeps default arguments readonly while custom mode is off', async () => {
    const html = await renderArguments(false)
    expect(html).not.toContain('-t DailyTask -e / -t 1 -e')
    expect(html).toContain('readonly')
    expect(html).not.toContain('OtherTask')
  })

  it('allows editing without rewriting the entered arguments', async () => {
    const html = await renderArguments(true)
    expect(html).toContain('value="-t OtherTask -h"')
    expect(html).not.toContain('readonly')
  })

  it('inherits the account configuration lock from its form', async () => {
    const html = await renderArguments(true, true)
    expect(html).toMatch(/<input[^>]*disabled/)
    expect(html).toMatch(/<button[^>]*disabled/)
  })
})
