import { describe, expect, it } from 'vitest'

import type {
  Emulator2AvdComponentItem,
  Emulator2AvdInstanceOptionsOut,
  WSEmulator2AvdInstallProgressData,
} from '@/api'
import {
  MEMORY_AUTO,
  canResume,
  componentState,
  createOptions,
  defaultAvdOptions,
  hasBlockingFailure,
  isJobRunning,
  jobPercent,
  optionsChanges,
  optionsFromOut,
  precheckLevel,
  samePath,
} from './avdLogic'

const job = (
  over: Partial<WSEmulator2AvdInstallProgressData>
): WSEmulator2AvdInstallProgressData => ({
  jobId: 'j',
  root: 'E:\\avd',
  stage: 'downloading',
  status: 'running',
  ...over,
})

const component = (over: Partial<Emulator2AvdComponentItem>): Emulator2AvdComponentItem => ({
  id: 'emulator',
  name: 'Android Emulator',
  installed: false,
  downloadedBytes: 0,
  ...over,
})

describe('instance options', () => {
  it('defaults follow the user-decided values', () => {
    expect(defaultAvdOptions()).toEqual({
      resolution: '720',
      memoryMb: MEMORY_AUTO,
      balloon: true,
      guestAngle: false,
      headless: true,
    })
  })

  it('reads auto memory as auto even though the backend sends a fallback value', () => {
    const out: Emulator2AvdInstanceOptionsOut = {
      resolution: '1080',
      memoryAuto: true,
      memoryMb: 4096,
      balloon: false,
      guestAngle: true,
      headless: false,
    }
    expect(optionsFromOut(out)).toEqual({
      resolution: '1080',
      memoryMb: MEMORY_AUTO,
      balloon: false,
      guestAngle: true,
      headless: false,
    })
    expect(optionsFromOut({ ...out, memoryAuto: false, memoryMb: 5120 }).memoryMb).toBe(5120)
  })

  it('only sends changed fields, and auto memory as 0', () => {
    const base = defaultAvdOptions()
    expect(optionsChanges(base, { ...base })).toEqual({})
    expect(optionsChanges({ ...base, memoryMb: 5120 }, { ...base, balloon: false })).toEqual({
      memoryMb: MEMORY_AUTO,
      balloon: false,
    })
  })

  it('create leaves auto memory out', () => {
    expect(createOptions(defaultAvdOptions()).memoryMb).toBeNull()
    expect(createOptions({ ...defaultAvdOptions(), memoryMb: 6144 }).memoryMb).toBe(6144)
  })
})

describe('prechecks', () => {
  it('grades each result', () => {
    expect(precheckLevel({ id: 'disk', title: '', ok: true, blocking: true })).toBe('ok')
    expect(precheckLevel({ id: 'disk', title: '', ok: false, blocking: true })).toBe('error')
    expect(precheckLevel({ id: 'vulkan', title: '', ok: false, blocking: false })).toBe('warning')
    expect(precheckLevel({ id: 'acceleration', title: '', ok: null, blocking: true })).toBe(
      'unknown'
    )
  })

  it('only blocking failures stop the boot', () => {
    expect(hasBlockingFailure([{ id: 'vulkan', title: '', ok: false, blocking: false }])).toBe(
      false
    )
    expect(hasBlockingFailure([{ id: 'memory', title: '', ok: false, blocking: true }])).toBe(true)
    expect(hasBlockingFailure(undefined)).toBe(false)
  })
})

describe('download state', () => {
  it('compares Windows roots loosely', () => {
    expect(samePath('E:\\emu-tmp\\root1\\', 'e:/emu-tmp/root1')).toBe(true)
    expect(samePath('E:\\a', 'E:\\b')).toBe(false)
    expect(samePath('', 'E:\\a')).toBe(false)
  })

  it('offers resume after a cancel, a failure, or a partial download', () => {
    expect(canResume([], job({ status: 'cancelled', stage: 'cancelled' }))).toBe(true)
    expect(canResume([], job({ status: 'failed', stage: 'failed' }))).toBe(true)
    expect(canResume([component({ downloadedBytes: 100 })], null)).toBe(true)
    expect(canResume([component({})], null)).toBe(false)
    expect(canResume([component({ downloadedBytes: 100 })], job({}))).toBe(false)
    expect(isJobRunning(job({}))).toBe(true)
  })

  it('component state', () => {
    expect(componentState(component({ installed: true }))).toBe('ready')
    expect(componentState(component({ downloadedBytes: 1 }))).toBe('partial')
    expect(componentState(component({}))).toBe('missing')
  })

  it('progress follows the stage', () => {
    expect(jobPercent(null)).toBeNull()
    expect(jobPercent(job({ percent: 41.6 }))).toBe(42)
    expect(jobPercent(job({ stage: 'extracting', percent: 90, extractPercent: 12.2 }))).toBe(12)
    expect(jobPercent(job({ status: 'success', stage: 'completed' }))).toBe(100)
    expect(jobPercent(job({ percent: null }))).toBeNull()
  })
})
