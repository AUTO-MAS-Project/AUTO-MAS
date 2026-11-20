import { EventEmitter } from 'node:events'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { PassThrough, Writable } from 'node:stream'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import { validateAnalyticsEvent } from './analyticsPolicy'
import { DesktopSessionService } from './desktopSessionService'

const analytics = vi.hoisted(() => ({ getContext: vi.fn(), recordMainEvent: vi.fn() }))
const host = vi.hoisted(() => ({
  report: vi.fn(),
  command: vi.fn(),
  connect: vi.fn(),
  exit: vi.fn(),
}))

vi.mock('../ipc/initializationHandlers', () => ({
  getLocalApiEndpoint: () => 'http://127.0.0.1:36164',
}))
vi.mock('electron', () => ({ session: {} }))
vi.mock('./instanceConfig', () => ({}))
vi.mock('./analyticsService', () => ({ analyticsService: analytics }))
vi.mock('node:child_process', () => ({
  spawn: () => {
    const child = new EventEmitter()
    host.exit.mockImplementation(() => child.emit('exit'))
    const stdout = new PassThrough()
    const stderr = new PassThrough()
    const report = (event: object) => stdout.write(`${JSON.stringify(event)}\n`)
    host.report.mockImplementation(report)
    const stdin = new Writable({
      write(chunk, _encoding, done) {
        const { action, approvedRepairs } = JSON.parse(String(chunk))
        host.command(action)
        if (action === 'connect') {
          report(host.connect() ?? { event: 'state', state: 'connected', sessionId: 7 })
        }
        if (action === 'check') {
          const ready = host.connect.mock.calls.length > 0
          report({
            event: 'diagnostics',
            checks: [{ code: 'child_enabled', ok: ready, required: true }],
            repairs: ready ? [] : ['child_enabled'],
          })
        }
        if (action === 'repair' && approvedRepairs?.includes('child_enabled')) {
          report({
            event: 'diagnostics',
            checks: [{ code: 'child_enabled', ok: true, required: true }],
          })
          report({ event: 'repair_finished' })
        }
        if (action === 'close') report({ event: 'state', state: 'idle' })
        if (action === 'shutdown') {
          stdout.end()
          stderr.end()
          queueMicrotask(() => host.exit())
        }
        done()
      },
    })
    queueMicrotask(() => report({ event: 'ready' }))
    return Object.assign(child, { stdin, stdout, stderr })
  },
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetAllMocks()
})

it('closes a host that is still being prepared by the first check', async () => {
  const root = mkdtempSync(join(tmpdir(), 'mas-desktop-close-during-check-'))
  const runtime = Promise.withResolvers<Response>()
  vi.stubGlobal('fetch', async (url: string) =>
    new URL(url).pathname.endsWith('/describe') ? runtime.promise : Response.json({ updated: true })
  )
  const service = new DesktopSessionService(vi.fn(), vi.fn(), vi.fn())
  const check = service.check()
  const close = service.close()
  runtime.resolve(
    Response.json({ python: 'python', launcher: join(root, 'bootstrap.py'), root, source: root })
  )
  try {
    await Promise.all([check, close])
    expect(host.command.mock.calls).toEqual([['close'], ['shutdown']])
    expect(service.snapshot.state).toBe('idle')
  } finally {
    await service.close()
    rmSync(root, { recursive: true, force: true })
  }
})

it('repairs only through the approved repair operation', async () => {
  const root = mkdtempSync(join(tmpdir(), 'mas-desktop-repair-'))
  vi.stubGlobal('fetch', async (url: string) =>
    new URL(url).pathname.endsWith('/describe')
      ? Response.json({
          python: 'python',
          launcher: join(root, 'bootstrap.py'),
          root,
          source: root,
        })
      : Response.json({ updated: true })
  )
  const service = new DesktopSessionService(vi.fn(), vi.fn(), vi.fn())
  host.connect.mockReturnValue({ event: 'state', state: 'idle', code: 'environment_blocked' })
  try {
    expect(await service.check()).toMatchObject({ state: 'blocked', repairPlan: ['child_enabled'] })
    expect(
      await service.start(
        { queueIds: [], mode: 'proxy', resolution: '1080p' },
        1n,
        [0, 0, 100, 100]
      )
    ).toMatchObject({ code: 'environment_blocked' })
    expect(await service.repair(['term_service_disabled'])).toBe('environment_changed')
    expect(host.command).not.toHaveBeenCalledWith('repair')
    expect(await service.repair(['child_enabled'])).toBeUndefined()
    expect(service.snapshot).toMatchObject({ state: 'idle', repairPlan: [] })
    expect(host.command.mock.calls.filter(([action]) => action === 'repair')).toEqual([['repair']])
  } finally {
    await service.close()
    rmSync(root, { recursive: true, force: true })
  }
})

it.each([
  { idle: true, hostExited: false, externalStart: false },
  { idle: false, hostExited: false, externalStart: false },
  { idle: true, hostExited: true, externalStart: false },
  { idle: true, hostExited: false, externalStart: true },
])(
  'checks and waits for old tasks before reconnecting ($idle, $hostExited, $externalStart)',
  async ({ idle, hostExited, externalStart }) => {
    const root = mkdtempSync(join(tmpdir(), 'mas-desktop-reconnect-'))
    const queueId = '00000000-0000-4000-8000-000000000001'
    const request = { mode: 'proxy', resolution: '1080p' } as const
    const pendingStop = Promise.withResolvers<Response>()
    const stopRequested = vi.fn()
    vi.stubGlobal('fetch', async (url: string) => {
      switch (new URL(url).pathname) {
        case '/internal/desktop-session/describe':
          return Response.json({
            python: 'python',
            launcher: join(root, 'bootstrap.py'),
            root,
            source: root,
          })
        case '/internal/desktop-session/release':
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
      await service.start({ ...request, queueIds: externalStart ? [] : [queueId] }, 1n, bounds)
      expect(service.snapshot.executing).toBe(!externalStart)
      if (hostExited) host.exit()
      else host.report({ event: 'state', state: 'disconnected' })
      expect(service.snapshot.state).toBe('disconnected')
      if (externalStart) {
        // A task started via the backend can exist before the first state poll.
        await vi.waitFor(() => expect(stopRequested).toHaveBeenCalledOnce(), { timeout: 2000 })
        pendingStop.resolve(Response.json({ idle: true }))
        await vi.waitFor(() => expect(service.snapshot.code).toBe('executor_interrupted'))
      }
      await service.check()
      host.command.mockClear()

      const reconnect = service.start({ ...request, queueIds: [] }, 1n, bounds)
      if (!externalStart) {
        await vi.waitFor(() => expect(stopRequested).toHaveBeenCalledOnce())
        expect(host.command).not.toHaveBeenCalled()
        pendingStop.resolve(Response.json({ idle }))
      }

      if (idle) {
        expect(await reconnect).toEqual({ queues: [] })
        expect(stopRequested).toHaveBeenCalledOnce()
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
  }
)

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
        return Response.json({
          python: 'python',
          launcher: join(root, 'bootstrap.py'),
          root,
          source: root,
        })
      case '/internal/desktop-session/release':
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
  const confirmTaskDispatch = vi.fn()
  const notifyEmulatorOnly = vi.fn()
  try {
    const result = await service.start(
      { queueIds: [queueId], mode: 'proxy', resolution: '1080p' },
      1n,
      [0, 0, 100, 100],
      { confirmTakeover: async () => false, confirmTaskDispatch, notifyEmulatorOnly }
    )
    expect(result.queues[0]?.taskId).toBe(taskId)
    expect(confirmTaskDispatch).not.toHaveBeenCalled()
    expect(notifyEmulatorOnly).not.toHaveBeenCalled()
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
    expect(requests.at(-1)).toBe('/internal/desktop-session/release')
    expect(requests).not.toContain('/internal/desktop-session/handoff')
    expect(service.snapshot.executing).toBe(false)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

it('preserves the session-changed error when the backend rejects dispatch', async () => {
  const root = mkdtempSync(join(tmpdir(), 'mas-desktop-dispatch-conflict-'))
  vi.stubGlobal('fetch', async (url: string) => {
    if (new URL(url).pathname.endsWith('/describe'))
      return Response.json({
        python: 'python',
        launcher: join(root, 'bootstrap.py'),
        root,
        source: root,
      })
    if (url.endsWith('/queues'))
      return Response.json(
        { code: 'session_changed', status: 'error', message: '桌面分身连接已断开' },
        { status: 409 }
      )
    return Response.json({ updated: true, idle: true })
  })
  const tasksStarted = vi.fn()
  const service = new DesktopSessionService(vi.fn(), vi.fn(), tasksStarted)
  try {
    const result = await service.start(
      { queueIds: ['00000000-0000-4000-8000-000000000001'], mode: 'proxy', resolution: '1080p' },
      1n,
      [0, 0, 100, 100]
    )
    expect(result).toEqual({ code: 'session_changed', queues: [] })
    expect(tasksStarted).not.toHaveBeenCalled()
  } finally {
    await service.close()
    rmSync(root, { recursive: true, force: true })
  }
})

it.each([
  { adopted: false, taskState: 'none', expected: undefined },
  { adopted: false, taskState: 'finished', expected: undefined },
  { adopted: false, taskState: 'running', expected: 'close' },
  { adopted: false, taskState: 'unknown', expected: 'close' },
  { adopted: true, taskState: 'none', expected: 'close-adopted' },
] as const)(
  'checks manual close for adopted=$adopted with tasks $taskState',
  async ({ adopted, taskState, expected }) => {
    const root = mkdtempSync(join(tmpdir(), 'mas-desktop-close-policy-'))
    host.connect.mockReturnValue({ event: 'state', state: 'connected', sessionId: 7, adopted })
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const endpoint = new URL(url).pathname
      if (endpoint.endsWith('/describe'))
        return Response.json({
          python: 'python',
          launcher: join(root, 'bootstrap.py'),
          root,
          source: root,
        })
      if (endpoint.endsWith('/queues'))
        return Response.json({
          results: [{ queueId: 'test-queue', taskId: 'test-task', targetKind: 'queue' }],
        })
      if (endpoint.endsWith('/preview-closing'))
        return taskState === 'unknown' && JSON.parse(String(init?.body)).closing
          ? new Response(null, { status: 503 })
          : Response.json({ idle: taskState === 'none' || taskState === 'finished' })
      return Response.json({ updated: true, idle: true })
    })
    const service = new DesktopSessionService(vi.fn(), vi.fn(), vi.fn())
    try {
      const start = await service.start(
        {
          queueIds: taskState === 'none' ? [] : ['test-queue'],
          mode: 'proxy',
          resolution: '1080p',
        },
        1n,
        [0, 0, 100, 100]
      )
      expect(start.code).toBeUndefined()
      if (taskState === 'unknown') {
        await expect(service.getClosePrompt(true)).rejects.toThrow('http_503')
      } else {
        expect(await service.getClosePrompt(true)).toBe(expected)
        expect(await service.getClosePrompt(false)).toBe(adopted ? 'close-adopted' : 'close')
      }
    } finally {
      await service.close()
      rmSync(root, { recursive: true, force: true })
    }
  }
)

it('reports an emulator-only selection without connecting or submitting tasks', async () => {
  const target = {
    queueId: 'emulator',
    taskId: '',
    targetKind: 'script',
    label: 'Emulator task',
    code: 'emulator_required',
  }
  vi.stubGlobal('fetch', async (url: string, options: RequestInit) => {
    expect(new URL(url).pathname).toBe('/internal/desktop-session/queues')
    expect(JSON.parse(String(options.body))).toEqual({
      queueIds: [target.queueId],
      previewOnly: true,
    })
    return Response.json({ results: [target] })
  })
  const notifyEmulatorOnly = vi.fn()
  const confirmTaskDispatch = vi.fn()
  const service = new DesktopSessionService(vi.fn(), vi.fn(), vi.fn())
  const result = await service.start(
    { queueIds: [target.queueId], mode: 'proxy', resolution: '1080p' },
    1n,
    [0, 0, 100, 100],
    { confirmTakeover: async () => false, confirmTaskDispatch, notifyEmulatorOnly }
  )
  expect(result).toEqual({ queues: [target] })
  expect(notifyEmulatorOnly).toHaveBeenCalledWith([target])
  expect(confirmTaskDispatch).not.toHaveBeenCalled()
  expect(host.connect).not.toHaveBeenCalled()
  expect(analytics.recordMainEvent).not.toHaveBeenCalled()
})

it.each([
  { choice: 'split', dispatchedIds: ['desktop', 'emulator'], mainIds: ['emulator'] },
  { choice: 'desktop', dispatchedIds: ['desktop'] },
  { choice: 'cancel', dispatchedIds: [] },
] as const)(
  'waits for the mixed-session choice ($choice)',
  async ({ choice, dispatchedIds, ...expected }) => {
    const root = mkdtempSync(join(tmpdir(), 'mas-desktop-mixed-'))
    const preview = [
      { queueId: 'desktop', taskId: '', targetKind: 'script', label: 'Desktop task', code: '' },
      {
        queueId: 'emulator',
        taskId: '',
        targetKind: 'queue',
        label: 'Emulator queue',
        code: 'emulator_required',
      },
      {
        queueId: 'unsupported',
        taskId: '',
        targetKind: 'script',
        label: 'Unsupported task',
        code: 'unsupported_target',
      },
    ]
    const submissions: unknown[] = []
    vi.stubGlobal('fetch', async (url: string, options: RequestInit) => {
      const endpoint = new URL(url).pathname
      if (endpoint.endsWith('/describe'))
        return Response.json({
          python: 'python',
          launcher: join(root, 'bootstrap.py'),
          root,
          source: root,
        })
      if (endpoint.endsWith('/queues')) {
        const body = JSON.parse(String(options.body))
        if (body.previewOnly) return Response.json({ results: preview })
        submissions.push(body)
        return Response.json({
          results: preview
            .filter(target => body.queueIds.includes(target.queueId))
            .map(target => ({ ...target, taskId: `task-${target.queueId}`, code: '' })),
        })
      }
      return Response.json({ updated: true, idle: true })
    })

    const service = new DesktopSessionService(vi.fn(), vi.fn(), vi.fn())
    try {
      const result = await service.start(
        { queueIds: preview.map(target => target.queueId), mode: 'proxy', resolution: '1080p' },
        1n,
        [0, 0, 100, 100],
        {
          confirmTakeover: async () => false,
          notifyEmulatorOnly: vi.fn(),
          confirmTaskDispatch: async ({ desktop, main }) => {
            expect(host.connect).not.toHaveBeenCalled()
            expect(submissions).toEqual([])
            expect(desktop.map(target => target.label)).toEqual(['Desktop task'])
            expect(main.map(target => target.label)).toEqual(['Emulator queue'])
            return choice
          },
        }
      )
      expect(result.code).toBeUndefined()
      if (choice === 'cancel') expect(host.connect).not.toHaveBeenCalled()
      expect(submissions).toEqual(
        dispatchedIds.length
          ? [
              {
                queueIds: dispatchedIds,
                ...('mainIds' in expected ? { mainSessionQueueIds: expected.mainIds } : {}),
              },
            ]
          : []
      )
    } finally {
      await service.close()
      rmSync(root, { recursive: true, force: true })
    }
  }
)
