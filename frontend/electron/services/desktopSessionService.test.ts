import { EventEmitter } from 'node:events'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { PassThrough, Writable } from 'node:stream'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import { validateAnalyticsEvent } from './analyticsPolicy'
import { DesktopSessionService } from './desktopSessionService'

const backend = vi.hoisted(() => ({ startBackend: vi.fn(), stopBackend: vi.fn() }))
const analytics = vi.hoisted(() => ({ getContext: vi.fn(), recordMainEvent: vi.fn() }))

vi.mock('../ipc/initializationHandlers', () => ({
  getBackendService: () => backend,
  getLocalApiEndpoint: () => 'http://127.0.0.1:36164',
}))
vi.mock('electron', () => ({ session: {} }))
vi.mock('./instanceConfig', () => ({}))
vi.mock('./analyticsService', () => ({ analyticsService: analytics }))
vi.mock('node:child_process', () => ({
  spawn: () => {
    const stdout = new PassThrough()
    const stderr = new PassThrough()
    const report = (event: object) => stdout.write(`${JSON.stringify(event)}\n`)
    const stdin = new Writable({
      write(chunk, _encoding, done) {
        const { action } = JSON.parse(String(chunk))
        if (action === 'connect') report({ event: 'state', state: 'connected', sessionId: 7 })
        if (action === 'close') report({ event: 'state', state: 'idle' })
        done()
      },
      final(done) {
        stdout.end()
        stderr.end()
        done()
      },
    })
    queueMicrotask(() => report({ event: 'ready' }))
    return Object.assign(new EventEmitter(), { stdin, stdout, stderr })
  },
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetAllMocks()
})

it('reconnects only after stopping a parent whose handoff response was lost', async () => {
  const root = mkdtempSync(join(tmpdir(), 'mas-desktop-handoff-'))
  let parentState: 'ready' | 'draining' | 'stopped' = 'ready'
  backend.stopBackend.mockImplementation(async () => {
    parentState = 'stopped'
    return { success: true }
  })
  backend.startBackend.mockImplementation(async () => {
    // A live Runtime reports success from startBackend without restarting the draining process.
    if (parentState === 'stopped') parentState = 'ready'
    return { success: true }
  })
  vi.stubGlobal('fetch', async (url: string) => {
    switch (new URL(url).pathname) {
      case '/internal/desktop-session/describe':
        return Response.json({ python: 'python', root, source: root })
      case '/internal/desktop-session/process-scope':
        return Response.json({ updated: true })
      case '/internal/desktop-session/handoff':
        parentState = 'draining'
        throw new DOMException('Handoff response timed out', 'TimeoutError')
      default:
        throw new Error(`Unexpected request to ${url}`)
    }
  })

  const transitions = vi.fn()
  const service = new DesktopSessionService(vi.fn(), transitions, vi.fn(), () => false, vi.fn())
  try {
    const result = await service.start(
      { queueIds: ['00000000-0000-4000-8000-000000000001'], mode: 'proxy', resolution: '1080p' },
      1n,
      [0, 0, 100, 100]
    )
    expect(result.code).toBe('handoff_unconfirmed')
    const dispatchEvents = analytics.recordMainEvent.mock.calls
      .map(([, event]) => event)
      .filter(event => event.name === 'task_start_result')
    expect(dispatchEvents).toEqual([
      {
        name: 'task_start_result',
        props: {
          source: 'desktop_session',
          mode: 'AutoProxy',
          target_kind: 'unknown',
          outcome: 'failure',
          duration_bucket: expect.any(String),
        },
      },
    ])
    expect(validateAnalyticsEvent(dispatchEvents[0], false)).toEqual(dispatchEvents[0])
    expect(validateAnalyticsEvent(dispatchEvents[0], true)).toBeNull()
    await vi.waitFor(() => expect(transitions).toHaveBeenCalledWith(false, true), { timeout: 3000 })
    expect(parentState).toBe('ready')
  } finally {
    try {
      await service.close(true)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  }
})
