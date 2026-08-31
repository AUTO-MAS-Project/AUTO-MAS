import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./CommunityActivityView.vue', import.meta.url), 'utf8')

describe('CommunityActivityView structure', () => {
  it('keeps independent game cards in a half-width draggable grid', () => {
    expect(source).toContain('grid-template-columns: repeat(2, minmax(0, 1fr));')
    expect(source).toContain('grid-auto-rows: 1fr;')
    expect(source).toContain('handle=".activity-drag-handle"')
    expect(source).toContain('<component :is="gameVisual(element.game).icon" />')
  })

  it('uses the i18n catalog and does not add a card-level scroll owner', () => {
    expect(source).toContain("t('gamesign.activity.title')")
    expect(source).toContain("t('gamesign.activity.status.failed')")
    expect(source).not.toContain('overflow: auto')
    expect(source).not.toContain('overflow-y: auto')
  })

  it('maps every supported game to a distinct visual element', () => {
    for (const game of ['明日方舟', '终末地', '原神', '星穹铁道', '绝区零']) {
      expect(source).toContain(`${game}:`)
    }
  })
})
