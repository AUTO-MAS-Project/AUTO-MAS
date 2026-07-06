import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const preloadSource = readFileSync(new URL('../../electron/preload.ts', import.meta.url), 'utf8')
const declarationSource = readFileSync(new URL('./electron.d.ts', import.meta.url), 'utf8')

describe('Electron API types', () => {
  it('shares Electron file filter types without any', () => {
    expect(preloadSource).toContain('selectFile: (filters?: FileFilter[])')
    expect(declarationSource).toContain('selectFile: (filters?: FileFilter[])')
  })

  it('accepts unknown logger arguments without disabling type checking', () => {
    expect(preloadSource).not.toMatch(/(?:debug|info|warn|error): \(\.\.\.args: any\[\]\)/)
    expect(declarationSource).not.toMatch(/(?:debug|info|warn|error): \(\.\.\.args: any\[\]\)/)
  })
})
