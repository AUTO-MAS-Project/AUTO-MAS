import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./CommunityActivityView.vue', import.meta.url), 'utf8')
const pageSource = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')
const signSource = readFileSync(new URL('./TabGameSign.vue', import.meta.url), 'utf8')
const toolsSource = readFileSync(new URL('../tools/index.vue', import.meta.url), 'utf8')

describe('CommunityActivityView structure', () => {
  it('keeps independent game cards in a half-width draggable grid', () => {
    expect(source).toContain('grid-template-columns: repeat(2, minmax(0, 1fr));')
    expect(source).toContain('grid-auto-rows: 1fr;')
    expect(source).toContain('handle=".activity-drag-handle"')
    expect(source).toContain('class="activity-game-image"')
    expect(source).toContain('v-if="gameVisual(element.game).image"')
    expect(source).toContain('v-else :is="gameVisual(element.game).icon"')
    expect(source).toContain(':class="[\'activity-card\', gameVisual(element.game).uiClass]"')
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
    expect(source.match(/image: \w+NoteImage/g)).toHaveLength(5)
    expect(source.match(/backgroundImage: \w+NoteBackgroundImage/g)).toHaveLength(5)
    expect(
      source.match(/uiClass: 'activity-card--(arknights|endfield|genshin|star-rail|zenless)'/g)
    ).toHaveLength(5)
    expect(source).toContain('@/assets/community-notes/arknights.png')
    expect(source).toContain('@/assets/community-notes/zenless.png')
    expect(source).toContain('@/assets/community-notes/arknights-background.png')
    expect(source).toContain('@/assets/community-notes/endfield-background.png')
    expect(source).toContain('@/assets/community-notes/genshin-background.png')
    expect(source).toContain('@/assets/community-notes/star-rail-background.png')
    expect(source).toContain('@/assets/community-notes/zenless-background.png')
    expect(source).toContain("'--activity-background-image'")
    expect(source).toContain('.activity-card::before')
    expect(source).toMatch(/background-image:\s*var\(--activity-background-image\);/)
    expect(source).toContain('opacity: 0.24;')
    expect(source).toContain('.activity-card--endfield::before')
    expect(source).toContain('.activity-card--zenless::before')
  })

  it('shows only confirmed daily progress and separates recurring information', () => {
    expect(source).toContain('<div v-if="hasProgress(element)" class="activity-summary">')
    expect(source).not.toContain("t('gamesign.activity.noProgress')")
    expect(source).toContain('v-for="task in dailyTasks(element)"')
    expect(source).toContain('v-for="task in weeklyTasks(element)"')
    expect(source).toContain("t('gamesign.activity.weeklyTasks')")
    expect(source).toContain('{{ task.status }}')
    expect(source).toContain('{{ resource.status }}')
    expect(source).toContain('v-if="hasTaskProgress(task)"')
    expect(source).toContain('v-if="hasResourceProgress(resource)"')
    expect(source).toContain('background-size: cover;')
    expect(source).not.toContain('经验')
    expect(source).toContain('activity-section--resources')
    expect(source).toContain('grid-column: 1 / -1;')
    expect(source).toContain('column-gap: 12px;')
    expect(source).toContain('@media (max-width: 560px)')
  })

  it('keeps the note cards compact without clipping their confirmed data', () => {
    expect(source).toContain('padding: 8px 12px;')
    expect(source).toContain('min-height: 0;')
    expect(source).toContain('padding: 8px;')
    expect(source).toContain('padding: 6px;')
    expect(source).toContain('margin-top: 8px;')
    expect(source).not.toContain('min-height: 240px;')
    expect(source).not.toContain('margin-top: auto;')
  })

  it('keeps one vertical page scroll owner and removes page-level gradients', () => {
    expect(pageSource).toContain('overflow: visible;')
    expect(pageSource).not.toContain('::-webkit-scrollbar')
    expect(toolsSource).toContain('overflow: visible;')
    expect(toolsSource).not.toContain('::-webkit-scrollbar')
    expect(toolsSource).not.toContain('linear-gradient')
  })

  it('stacks narrow account rows while preserving centered tag width', () => {
    expect(signSource).toContain('@media (max-width: 860px)')
    expect(signSource).toContain('grid-template-columns: 32px minmax(0, 1fr) auto;')
    expect(signSource).toContain('min-width: 76px;')
    expect(signSource).toContain('justify-content: center;')
  })
})
