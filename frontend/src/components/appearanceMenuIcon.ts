import { h, type Component, type VNode } from 'vue'

import type { AppearanceMenuIconKey, AppearanceMenuIcons } from '@/types/appearance'

export function createAppearanceMenuIcon(
  key: AppearanceMenuIconKey,
  fallback: Component,
  menuIcons: AppearanceMenuIcons | undefined
): VNode {
  const url = menuIcons?.[key]
  if (!url) return h(fallback)

  return h('img', {
    class: 'appearance-menu-icon',
    src: url,
    width: 24,
    height: 24,
    style: { objectFit: 'contain', display: 'block' },
    alt: '',
    'aria-hidden': 'true',
  })
}
