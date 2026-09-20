import { readFileSync } from 'node:fs'
import { compile } from '@vue/compiler-dom'
import * as Vue from 'vue'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./MaaEndUserEdit.vue', import.meta.url), 'utf8')
const anchor = source.match(/<a-anchor\s[\s\S]*?\/>/)?.[0] ?? ''

describe('MaaEnd section navigation', () => {
  it('prevents the native anchor from replacing the hash route', () => {
    // Compile the actual binding so the test exercises Vue event modifiers.
    const clickBinding = anchor.match(/@click[^\s>]*/)?.[0] ?? ''
    const { code } = compile(`<a href="#section-task" ${clickBinding}>Task</a>`, {
      mode: 'function',
    })
    const render = new Function('Vue', code)(Vue)
    const vnode = render({}, [])
    const event = new Event('click', { cancelable: true })
    vnode.props.onClick(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('scrolls the application content panel', () => {
    expect(anchor).toContain(':get-container="getAnchorContainer"')
    expect(source).toContain("document.querySelector<HTMLElement>('.content-area')")
  })
})
