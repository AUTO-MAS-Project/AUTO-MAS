import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, ref, shallowRef, type Ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import type { InstalledAppearance } from '@/types/appearance'

const themeMocks = vi.hoisted(() => ({
  state: null as null | {
    activeAppearance: Ref<InstalledAppearance | null>
    customBackgroundUrl: Ref<string>
    customSurfaceOpacity: Ref<number>
  },
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => themeMocks.state,
}))

import AppearanceDecoration from './AppearanceDecoration.vue'

const renderDecoration = async () =>
  (await renderToString(createSSRApp(AppearanceDecoration))).replace(/<!--[\s\S]*?-->/g, '')

describe('AppearanceDecoration', () => {
  beforeEach(() => {
    themeMocks.state = {
      activeAppearance: shallowRef(null),
      customBackgroundUrl: ref(''),
      customSurfaceOpacity: ref(1),
    }
  })

  it('renders a custom background without an appearance package', async () => {
    themeMocks.state!.customBackgroundUrl.value = 'data:image/png;base64,AA=='

    expect(await renderDecoration()).toContain('appearance-background')
  })

  it('keeps rendering a package background', async () => {
    themeMocks.state!.activeAppearance.value = {
      formatVersion: 1,
      id: 'demo',
      name: 'Demo',
      mode: 'dark',
      tokens: { colorPrimary: '#123456' },
      backgroundUrl: 'data:image/png;base64,AA==',
    }

    expect(await renderDecoration()).toContain('appearance-background')
  })

  it('renders no decoration without a background source', async () => {
    expect(await renderDecoration()).toBe('')
  })
})
