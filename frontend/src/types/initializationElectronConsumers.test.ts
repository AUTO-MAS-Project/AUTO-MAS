import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const consumerPaths = [
  '../utils/initializationDecision.ts',
  '../utils/skippedInitializationStartup.ts',
  '../views/Initialization/index.vue',
  '../views/Initialization/components/BackendStartStep.vue',
]

describe('typed initialization Electron API consumers', () => {
  it.each(consumerPaths)('%s uses the declared Electron API', path => {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8')

    expect(source).not.toContain('window.electronAPI as any')
    expect(source).not.toContain('(window.electronAPI as any)')
  })
})
