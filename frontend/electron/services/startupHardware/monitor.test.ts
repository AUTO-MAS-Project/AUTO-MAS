import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import { fileURLToPath } from 'node:url'
import { parseRuntimeEventLine } from '../runtime/ndjson'
import type { RuntimeStateEvent } from '../runtime/protocol'
import path from 'node:path'
import { expect, it, vi } from 'vite-plus/test'
import { StartupHardwareLog } from './localLog'
import { StartupAttempt } from './monitor'

async function withAttempt(run: (attempt: StartupAttempt) => void | Promise<void>) {
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
    await run(attempt)
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
    const clock = vi.spyOn(performance, 'now')
    try {
      for (const line of data.trim().split('\n')) {
        const event = parseRuntimeEventLine(line)!
        clock.mockReturnValue(Date.parse(event.timestamp))
        attempt.progress(event)
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
      clock.mockReturnValue(100)
      attempt.progress(state)
      clock.mockReturnValue(3200)
      attempt.progress({ ...state, stage: 'backend.health' })
      clock.mockReturnValue(6100)
      attempt.progress({
        ...state,
        stage: 'backend.run',
        status: 'running',
        details: { baseUrl: 'http://127.0.0.1:36163' },
      })
      clock.mockReturnValue(90_000)
      expect(attempt.snapshot()).toMatchObject({ backend_time: '5-15s' })
    } finally {
      clock.mockRestore()
    }
  }))

it('安装文件和后续 uv 传输合计，重复的字节进度只计算一次', () =>
  withAttempt(attempt => {
    const mib = 2 ** 20
    const transfer = attempt.beginDesktopDownload(1)
    transfer(8 * mib, undefined)
    transfer(64 * mib, undefined)
    transfer(64 * mib, undefined)
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
      current: mib,
    })
    expect(attempt.snapshot().downloaded).toBe('16-128MiB')
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
