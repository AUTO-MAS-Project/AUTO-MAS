import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import { fileURLToPath } from 'node:url'
import { parseRuntimeEventLine } from '../runtime/ndjson'
import type { RuntimeResultEvent, RuntimeStateEvent } from '../runtime/protocol'
import path from 'node:path'
import { expect, it, vi } from 'vite-plus/test'
import { StartupHardwareLog } from './localLog'
import { StartupAttempt } from './monitor'

async function withAttempt(
  run: (attempt: StartupAttempt, log: StartupHardwareLog) => void | Promise<void>
) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'mas-hardware-progress-'))
  const log = new StartupHardwareLog(directory)
  const attempt = new StartupAttempt(null, {
    log,
    directories: [],
    graphics: async () => ({}),
    scope: 'managed',
    acceleration: 'unknown',
  })
  try {
    await run(attempt, log)
  } finally {
    attempt.stop()
    await log.drain()
    await rm(directory, { recursive: true, force: true })
  }
}

it('按 Runtime 的状态帧记录依赖同步，在后端就绪时结束启动计时', () =>
  withAttempt(async attempt => {
    const data = await readFile(
      fileURLToPath(new URL('../runtime/__fixtures__/bootstrap-success.ndjson', import.meta.url)),
      'utf8'
    )
    const received = attempt.started + 30_000
    const clock = vi.spyOn(performance, 'now').mockReturnValue(received)
    try {
      for (const line of data.trim().split('\n')) {
        attempt.progress(parseRuntimeEventLine(line)!)
      }
      expect(attempt.snapshot()).toMatchObject({ dependencies_time: '1-5s' })
      const base = { protocol: 1, operationId: 'supervise', timestamp: '', sequence: 1 }
      attempt.progress({
        ...base,
        type: 'hello',
        command: 'backend supervise',
        capabilities: [],
        runtimeVersion: 'test',
      })
      const state: RuntimeStateEvent = {
        ...base,
        type: 'state',
        status: 'starting_backend',
        stage: 'backend.spawn',
        message: '',
        details: {},
      }
      clock.mockReturnValue(received + 100)
      attempt.progress({ ...state, timestamp: '2026-09-01T21:00:00Z' })
      clock.mockReturnValue(received + 3200)
      attempt.progress({ ...state, stage: 'backend.health' })
      clock.mockReturnValue(received + 6100)
      attempt.progress({
        ...state,
        timestamp: '2026-09-01T21:02:06Z',
        stage: 'backend.run',
        status: 'running',
        details: { baseUrl: 'http://127.0.0.1:36163' },
      })
      clock.mockReturnValue(received + 90_000)
      expect(attempt.snapshot()).toMatchObject({ backend_time: '5-15s' })
    } finally {
      clock.mockRestore()
    }
  }))

it('安装文件和后续 uv 传输合计，重复的字节进度只计算一次', () =>
  withAttempt(attempt => {
    const mib = 2 ** 20
    const transfer = attempt.beginDesktopDownload(1)!
    transfer(8 * mib, undefined)
    transfer(64 * mib, undefined)
    transfer(64 * mib, undefined)
    expect(attempt.snapshot().downloaded).toBe('16-128MiB')
    const base = { protocol: 1, operationId: 'bootstrap', timestamp: '', sequence: 1 }
    attempt.progress({
      ...base,
      type: 'hello',
      runtimeVersion: 'test',
      capabilities: [],
      command: 'bootstrap',
    })
    attempt.progress({
      ...base,
      type: 'progress',
      stage: 'uv.download',
      status: 'running',
      message: '',
      current: 64 * mib,
    })
    expect(attempt.snapshot().downloaded).toBe('128-1024MiB')
    attempt.stop()
    const switches = attempt.snapshot().source_switches
    expect(attempt.beginDesktopDownload(2)).toBeUndefined()
    expect(attempt.snapshot().source_switches).toBe(switches)
  }))

it('跨命令累计归档耗时，复用缓存和重复终态不会覆盖或重复计算', () =>
  withAttempt(attempt => {
    const archives = [
      { cached: false, downloadMs: 4_000, verifyMs: 500, unpackMs: 3_000 },
      { cached: true, downloadMs: 0, verifyMs: 0, unpackMs: 0 },
      { cached: false, downloadMs: 4_000, verifyMs: 600, unpackMs: 4_000 },
    ]
    const times = archives.map((startupArchive, i) => {
      const base = { protocol: 1, operationId: String(i), timestamp: '' }
      attempt.progress({
        ...base,
        type: 'hello',
        sequence: 1,
        command: 'bootstrap',
        capabilities: [],
        runtimeVersion: 'test',
      })
      const result: RuntimeResultEvent = {
        ...base,
        type: 'result',
        sequence: 2,
        success: true,
        code: 'OK',
        stage: 'bootstrap',
        status: 'ready_to_start',
        message: '',
        retryable: false,
        remediation: [],
        details: { startupArchive },
      }
      attempt.progress(result)
      attempt.progress(result)
      const { download_time, verify_time, unpack_time, cache_reused } = attempt.snapshot()
      return [download_time, verify_time, unpack_time, cache_reused]
    })
    expect(times).toEqual([
      ['1-5s', '<1s', '1-5s', 'no'],
      ['1-5s', '<1s', '1-5s', 'yes'],
      ['5-15s', '1-5s', '5-15s', 'yes'],
    ])
  }))

it('重建过的环境在同一次启动的后续检查中仍记为已重建', () =>
  withAttempt(attempt => {
    const commands = ['bootstrap', 'dependencies rebuild', 'bootstrap']
    const flags = commands.map((command, i) => {
      const base = { protocol: 1, operationId: String(i), timestamp: '' }
      attempt.progress({
        ...base,
        type: 'hello',
        sequence: 1,
        command,
        capabilities: [],
        runtimeVersion: 'test',
      })
      attempt.progress({
        ...base,
        type: 'result',
        sequence: 2,
        success: true,
        code: 'OK',
        stage: command === 'bootstrap' ? 'bootstrap' : 'dependencies.rebuild',
        status: 'ready_to_start',
        message: '',
        retryable: false,
        remediation: [],
        details: command === 'bootstrap' ? { unchanged: true } : {},
      })
      return attempt.snapshot().env_rebuilt
    })
    expect(flags).toEqual(['no', 'yes', 'yes'])
  }))

it('依赖下载切换文件时沿用 Runtime 已汇总的字节数', () =>
  withAttempt(attempt => {
    const base = { protocol: 1, operationId: 'bootstrap', timestamp: '', sequence: 1 }
    attempt.progress({
      ...base,
      type: 'hello',
      command: 'bootstrap',
      capabilities: [],
      runtimeVersion: 'test',
    })
    for (const [item, mib] of [
      ['a.whl', 8],
      ['b.whl', 20],
      ['c.whl', 120],
    ] as const) {
      attempt.progress({
        ...base,
        type: 'progress',
        stage: 'dependencies.sync',
        status: 'running',
        message: '',
        item,
        current: mib * 2 ** 20,
        bytesPerSecond: 1,
      })
    }
    expect(attempt.snapshot().downloaded).toBe('16-128MiB')
  }))

it('自动修复再次失败时保留两次现场，同一个失败传到初始化终态时只写一次', () =>
  withAttempt((attempt, log) => {
    const write = vi.spyOn(log, 'write')
    attempt.beginStage('dependency')('failure', 'PYTHON_VERSION_MISMATCH')
    attempt.beginStage('python')('failure', 'ENVIRONMENT_BROKEN')
    attempt.logResult('initialization', 'failure', 'python')
    const windows = write.mock.calls.filter(([event]) => event === '失败前15秒')
    expect(windows.map(([, row]) => row.stage)).toEqual(['dependency', 'python'])
  }))

it('停止采样后才失败时按真正的失败时刻过滤最近读数', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'mas-hardware-expired-'))
  const log = new StartupHardwareLog(dir)
  const attempt = new StartupAttempt(null, {
    log,
    directories: [],
    graphics: async () => ({}),
    scope: 'desktop',
    acceleration: 'unknown',
  })
  try {
    attempt.stop()
    const clock = vi.spyOn(performance, 'now').mockReturnValue(attempt.started + 61_000)
    try {
      attempt.logResult('backend', 'failure')
    } finally {
      clock.mockRestore()
    }
    await log.drain()
    const rows = (await readFile(path.join(dir, 'startup-hardware.log'), 'utf8'))
      .trim()
      .split('\n')
      .map(line => JSON.parse(line))
    expect(rows.find(row => row.event === '阶段结果')).toMatchObject({
      elapsed_ms: 61000,
      readings: {},
    })
    expect(rows.find(row => row.event === '阶段结果').sample_age_ms).toBeGreaterThan(15000)
    expect(rows.find(row => row.event === '失败前15秒').samples).toEqual([])
  } finally {
    attempt.stop()
    await log.drain()
    await rm(dir, { recursive: true, force: true })
  }
})
