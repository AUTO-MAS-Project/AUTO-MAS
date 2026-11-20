import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { expect, it, vi } from 'vite-plus/test'
import { StartupHardwareLog } from './localLog'
import { StartupAttempt } from './monitor'

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
