import { EventEmitter } from 'node:events'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { PassThrough, Writable } from 'node:stream'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import { validateAnalyticsEvent } from './analyticsPolicy'
import { DesktopSessionService } from './desktopSessionService'

const analytics = vi.hoisted(() => ({ getContext: vi.fn(), recordMainEvent: vi.fn() }))

vi.mock('../ipc/initializationHandlers', () => ({
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

it('dispatches and stops tasks through the same main backend', async () => {
  const root = mkdtempSync(join(tmpdir(), 'mas-desktop-dispatch-'))
  const queueId = '00000000-0000-4000-8000-000000000001'
  const taskId = '00000000-0000-4000-8000-000000000002'
  const requests: string[] = []
  vi.stubGlobal('fetch', async (url: string) => {
    const endpoint = new URL(url)
    expect(endpoint.origin).toBe('http://127.0.0.1:36164')
    requests.push(endpoint.pathname)
    switch (endpoint.pathname) {
      case '/internal/desktop-session/describe':
        return Response.json({ python: 'python', root, source: root })
      case '/internal/desktop-session/process-scope':
        return Response.json({ updated: true })
      case '/internal/desktop-session/queues':
        return Response.json({
          results: [{ queueId, taskId, targetKind: 'script', label: 'Probe', code: '' }],
        })
      case '/internal/desktop-session/stop':
        return Response.json({ idle: true })
      default:
        throw new Error(`Unexpected request to ${url}`)
    }
  })

  const tasksStarted = vi.fn()
  const service = new DesktopSessionService(vi.fn(), vi.fn(), tasksStarted)
  try {
    const result = await service.start(
      { queueIds: [queueId], mode: 'proxy', resolution: '1080p' },
      1n,
      [0, 0, 100, 100]
    )
    expect(result.queues[0]?.taskId).toBe(taskId)
    expect(tasksStarted).toHaveBeenCalledWith(result.queues)
    const dispatchEvents = analytics.recordMainEvent.mock.calls
      .map(([, event]) => event)
      .filter(event => event.name === 'task_start_result')
    expect(dispatchEvents).toEqual([
      {
        name: 'task_start_result',
        props: {
          source: 'desktop_session',
          mode: 'AutoProxy',
          target_kind: 'script',
          outcome: 'accepted',
          duration_bucket: expect.any(String),
        },
      },
    ])
    expect(validateAnalyticsEvent(dispatchEvents[0], false)).toEqual(dispatchEvents[0])
    expect(validateAnalyticsEvent(dispatchEvents[0], true)).toBeNull()
    await service.close()
    expect(requests).toContain('/internal/desktop-session/stop')
    expect(requests).not.toContain('/internal/desktop-session/handoff')
    expect(service.snapshot.executing).toBe(false)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})
