import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const mainSource = readFileSync(new URL('../main.ts', import.meta.url), 'utf8')
const scrollbarSource = readFileSync(new URL('./scrollbar.css', import.meta.url), 'utf8')

describe('global scrollbar styles', () => {
  it('loads the shared scrollbar stylesheet from the renderer entry', () => {
    expect(mainSource).toContain("import '@/styles/scrollbar.css'")
  })

  it('defines visible theme-aware scrollbars without a white track', () => {
    expect(scrollbarSource).toContain(':root.dark')
    expect(scrollbarSource).toContain('--app-scrollbar-track: transparent;')
    expect(scrollbarSource).toContain('*::-webkit-scrollbar')
    expect(scrollbarSource).not.toContain('display: none')
  })
})
