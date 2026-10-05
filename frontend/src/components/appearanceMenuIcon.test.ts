import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { createAppearanceMenuIcon } from './appearanceMenuIcon'

const fallback = () => h('svg')

describe('createAppearanceMenuIcon', () => {
  it('renders the package image when the selected key has a URL', () => {
    const vnode = createAppearanceMenuIcon('home', fallback, {
      home: 'data:image/png;base64,AA==',
    })

    expect(vnode.type).toBe('img')
    expect(vnode.props).toMatchObject({
      src: 'data:image/png;base64,AA==',
      alt: '',
      'aria-hidden': 'true',
      width: 24,
      height: 24,
    })
  })

  it('keeps the built-in icon when the package has no URL for the key', () => {
    const vnode = createAppearanceMenuIcon('settings', fallback, undefined)

    expect(vnode.type).toBe(fallback)
  })
})
