import { EventEmitter } from 'node:events'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { PassThrough, Writable } from 'node:stream'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import { validateAnalyticsEvent } from './analyticsPolicy'
import { DesktopSessionService } from './desktopSessionService'

const analytics = vi.hoisted(() => ({ getContext: vi.fn(), recordMainEvent: vi.fn() }))
const host = vi.hoisted(() => ({ report: vi.fn(), command: vi.fn() }))

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
    host.report.mockImplementation(report)
    const stdin = new Writable({
      write(chunk, _encoding, done) {
        const { action } = JSON.parse(String(chunk))
        host.command(action)
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

it.each([true, false])('waits for the old tasks before reconnecting (idle=%s)', async idle => {
  const root = mkdtempSync(join(tmpdir(), 'mas-desktop-reconnect-'))
  const queueId = '00000000-0000-4000-8000-000000000001'
  const request = { mode: 'proxy', resolution: '1080p' } as const
  const pendingStop = Promise.withResolvers<Response>()
  const stopRequested = vi.fn()
  vi.stubGlobal('fetch', async (url: string) => {
    switch (new URL(url).pathname) {
      case '/internal/desktop-session/describe':
        return Response.json({ python: 'python', root, source: root })
      case '/internal/desktop-session/process-scope':
        return Response.json({ updated: true })
      case '/internal/desktop-session/queues':
        return Response.json({
          results: [{ queueId, taskId: queueId, targetKind: 'script', label: 'Probe', code: '' }],
        })
      case '/internal/desktop-session/stop':
        stopRequested()
        return stopRequested.mock.calls.length === 1
          ? pendingStop.promise
          : Response.json({ idle: true })
      default:
        throw new Error(`Unexpected request to ${url}`)
    }
  })

  const service = new DesktopSessionService(vi.fn(), vi.fn(), vi.fn())
  const bounds: [number, number, number, number] = [0, 0, 100, 100]
  try {
    await service.start({ ...request, queueIds: [queueId] }, 1n, bounds)
    expect(service.snapshot.executing).toBe(true)
    host.report({ event: 'state', state: 'disconnected' })
    expect(service.snapshot.state).toBe('disconnected')
    host.command.mockClear()

    const reconnect = service.start({ ...request, queueIds: [] }, 1n, bounds)
    await vi.waitFor(() => expect(stopRequested).toHaveBeenCalledOnce())
    expect(host.command).not.toHaveBeenCalled()
    pendingStop.resolve(Response.json({ idle }))

    if (idle) {
      expect(await reconnect).toEqual({ queues: [] })
      expect(host.command.mock.calls.slice(0, 2)).toEqual([['close'], ['connect']])
    } else {
      expect(await reconnect).toEqual({ code: 'executor_failed', queues: [] })
      expect(host.command).not.toHaveBeenCalled()
      expect(service.snapshot).toMatchObject({
        state: 'disconnected',
        executing: true,
        sessionId: 7,
      })
    }
  } finally {
    pendingStop.resolve(Response.json({ idle: true }))
    await service.close()
    rmSync(root, { recursive: true, force: true })
  }
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
