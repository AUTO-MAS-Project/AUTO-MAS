import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./SatelliteAnimation.vue', import.meta.url), 'utf8')

describe('SatelliteAnimation backend readiness gating', () => {
  it('initializes the scene only after the backend connection is open', () => {
    const mounted = source.slice(source.indexOf('onMounted(async'))
    const readyIndex = mounted.indexOf('await waitBackendReady()')
    expect(readyIndex).toBeGreaterThan(-1)
    expect(mounted.indexOf('await initScene()')).toBeGreaterThan(readyIndex)
  })

  it('gates foreground-resume snapshot refresh and polling behind backend readiness', () => {
    expect(source).toContain('void waitBackendReady().then(')
  })

  it('disposes the readiness listener on unmount', () => {
    expect(source).toContain('disposeBackendReadyListener?.()')
  })
})
