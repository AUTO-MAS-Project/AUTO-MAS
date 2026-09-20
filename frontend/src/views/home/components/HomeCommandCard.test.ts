import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./HomeCommandCard.vue', import.meta.url), 'utf8')

describe('HomeCommandCard structure', () => {
  it('uses a responsive multi-select for quick-start tasks', () => {
    expect(source).toContain('v-model:value="selectedTaskIds"')
    expect(source).toContain('mode="multiple"')
    expect(source).toContain(':max-tag-count="\'responsive\'"')
    expect(source).toContain('selectedTaskIds: string[]')
    expect(source).toContain("'update:selectedTaskIds': [value: string[]]")
  })

  it('keeps the start action disabled while loading or no task is selected', () => {
    expect(source).toContain(':disabled="schedulerTasksLoading || selectedTaskIds.length === 0"')
    expect(source).not.toContain('selectedTaskId: string | null')
  })
})
