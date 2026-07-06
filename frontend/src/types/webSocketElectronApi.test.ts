import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const declarationSource = readFileSync(new URL('./electron.d.ts', import.meta.url), 'utf8')
const webSocketSource = readFileSync(
  new URL('../composables/useWebSocket.ts', import.meta.url),
  'utf8'
)

describe('WebSocket Electron API contract', () => {
  it('declares the restart capability exposed by preload', () => {
    expect(declarationSource).toContain('appRestart: () => Promise<void>')
  })

  it('uses typed backend and application controls', () => {
    expect(webSocketSource).not.toContain('(window.electronAPI as any)')
  })
})
