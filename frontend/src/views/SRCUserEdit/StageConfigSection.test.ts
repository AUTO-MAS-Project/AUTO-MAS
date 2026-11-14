import { describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '../../../../res/i18n/zh_CN.json'
import en from '../../../../res/i18n/en.json'
import ja from '../../../../res/i18n/ja.json'
import StageConfigSection from './StageConfigSection.vue'

vi.mock('@/components/FieldLabelWithHint.vue', () => ({ default: { render: () => null } }))

const secretActor = 'Cavern_of_Corrosion_Path_of_the_Secret_Actor'

describe('SRC existing relic selection', () => {
  it.each([
    ['zh-CN', zhCN, '遗器：密伶之径'],
    ['en', en, 'Path of the Secret Actor'],
    ['ja', ja, '遺物：密伶の路'],
  ] as const)(
    'shows Secret Actor as an option and the active stage in %s',
    async (locale, messages, label) => {
      const formData = {
        Stage: { Channel: 'Relic', Relic: secretActor, Materials: '-', Ornament: '-' },
      }
      const app = createSSRApp({
        render: () => h(StageConfigSection, { loading: false, formData }),
      })
      app.use(
        createI18n({ legacy: false, locale, flatJson: true, messages: { [locale]: messages } })
      )
      for (const [name, tag] of [
        ['ARow', 'div'],
        ['ACol', 'div'],
        ['AFormItem', 'div'],
        ['ASelect', 'select'],
        ['ASelectOption', 'option'],
        ['AInputNumber', 'input'],
        ['ATag', 'output'],
      ]) {
        app.component(
          name,
          defineComponent({
            setup:
              (_, { attrs, slots }) =>
              () =>
                h(tag, attrs, slots.default?.()),
          })
        )
      }

      const html = await renderToString(app)
      expect(html).toMatch(new RegExp(`<option[^>]*value="${secretActor}"[^>]*>${label}</option>`))
      expect(html).toMatch(new RegExp(`<output[^>]*>${label}</output>`))
      expect(formData.Stage.Relic).toBe(secretActor)
    }
  )
})
