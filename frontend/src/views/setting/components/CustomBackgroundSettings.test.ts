import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, ref, type Ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'

const themeMocks = vi.hoisted(() => ({
  state: null as null | {
    activeAppearance: Ref<null>
    customBackgroundPath: Ref<string>
    customBackgroundUrl: Ref<string>
    customSurfaceOpacity: Ref<number>
    setCustomBackground: () => Promise<void>
    clearCustomBackground: () => Promise<void>
    previewCustomSurfaceOpacity: (value: number) => void
    setCustomSurfaceOpacity: ReturnType<typeof vi.fn<(value: number) => Promise<void>>>
  },
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => themeMocks.state,
}))

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})

const passthrough = (name: string) =>
  defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { slots }) {
      return () => h('div', { class: name }, slots.default?.())
    },
  })

type SliderAttributes = {
  onChange?: (value: number) => void
  onAfterChange?: (value: number) => void
}

const renderSettings = async (
  onSliderSetup?: (attributes: SliderAttributes) => void
): Promise<string> => {
  const { default: CustomBackgroundSettings } = await import('./CustomBackgroundSettings.vue')
  const app = createSSRApp(CustomBackgroundSettings)
  app.use(i18n)
  for (const name of ['AAlert', 'ARow', 'ACol', 'ATooltip', 'AButton']) {
    app.component(name, passthrough(name))
  }
  app.component(
    'ASlider',
    defineComponent({
      name: 'ASlider',
      inheritAttrs: false,
      setup(_props, { attrs }) {
        onSliderSetup?.(attrs as SliderAttributes)
        return () =>
          h(
            'div',
            { class: 'ASlider' },
            `value:${String(attrs.value)};disabled:${String(attrs.disabled)}`
          )
      },
    })
  )
  return (await renderToString(app)).replace(/<!--[\s\S]*?-->/g, '')
}

describe('CustomBackgroundSettings', () => {
  beforeEach(() => {
    themeMocks.state = {
      activeAppearance: ref(null),
      customBackgroundPath: ref('wallpaper.png'),
      customBackgroundUrl: ref('data:image/png;base64,AA=='),
      customSurfaceOpacity: ref(0.8),
      setCustomBackground: async () => undefined,
      clearCustomBackground: async () => undefined,
      previewCustomSurfaceOpacity: value => {
        themeMocks.state!.customSurfaceOpacity.value = value
      },
      setCustomSurfaceOpacity: vi.fn(async value => {
        themeMocks.state!.customSurfaceOpacity.value = value
      }),
    }
  })

  it('previews drag changes and saves the final slider value', { timeout: 15000 }, async () => {
    let resolveSave: (() => void) | undefined
    const saveOpacity = themeMocks.state!.setCustomSurfaceOpacity
    saveOpacity.mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          resolveSave = () => {
            themeMocks.state!.customSurfaceOpacity.value = 0.55
            resolve()
          }
        })
    )

    const saving = await renderSettings(attributes => {
      attributes.onAfterChange?.(0.55)
    })

    expect(saving).toContain('value:0.8;disabled:false')
    expect(saveOpacity).toHaveBeenCalledTimes(1)
    expect(saveOpacity).toHaveBeenCalledWith(0.55)

    resolveSave?.()
    await Promise.resolve()
    await Promise.resolve()

    expect(await renderSettings()).toContain('value:0.55;disabled:false')
  })
})
