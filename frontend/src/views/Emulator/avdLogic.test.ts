import { describe, expect, it } from 'vitest'

import type {
  Emulator2AvdComponentItem,
  Emulator2AvdInstanceOptionsOut,
  WSEmulator2AvdInstallProgressData,
} from '@/api'
import {
  DEFAULT_MEMORY_MB,
  canResume,
  componentDetail,
  componentState,
  createOptions,
  defaultAvdOptions,
  hasBlockingFailure,
  isJobRunning,
  isRootAdded,
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
      memoryMb: 6144,
      balloon: true,
      guestAngle: false,
      headless: true,
    })
    expect(DEFAULT_MEMORY_MB).toBe(6144)
  })

  it('reads the instance memory as is', () => {
    const out: Emulator2AvdInstanceOptionsOut = {
      resolution: '1080',
      memoryMb: 4096,
      balloon: false,
      guestAngle: true,
      headless: false,
    }
    expect(optionsFromOut(out)).toEqual({
      resolution: '1080',
      memoryMb: 4096,
      balloon: false,
      guestAngle: true,
      headless: false,
    })
    expect(optionsFromOut({ ...out, memoryMb: null }).memoryMb).toBe(DEFAULT_MEMORY_MB)
  })

  it('only sends changed fields', () => {
    const base = defaultAvdOptions()
    expect(optionsChanges(base, { ...base })).toEqual({})
    expect(optionsChanges({ ...base, memoryMb: 5120 }, { ...base, balloon: false })).toEqual({
      memoryMb: 6144,
      balloon: false,
    })
  })

  it('create always sends a fixed memory', () => {
    expect(createOptions(defaultAvdOptions()).memoryMb).toBe(6144)
    expect(createOptions({ ...defaultAvdOptions(), memoryMb: 4096 }).memoryMb).toBe(4096)
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

describe('review fixes', () => {
  it('ready components show the installed version, no size; local SDK is marked', () => {
    const local = component({
      installed: true,
      version: '37.2.10',
      sizeBytes: 441_000_000,
      localSdk: true,
    })
    expect(componentDetail(local)).toEqual({
      version: '37.2.10',
      sizeBytes: null,
      localSdk: true,
      testPackage: false,
    })
    const downloaded = component({ installed: true, version: '37.1.11', sizeBytes: 441_000_000 })
    expect(componentDetail(downloaded)).toEqual({
      version: '37.1.11',
      sizeBytes: null,
      localSdk: false,
      testPackage: false,
    })
  })

  it('missing components show the version and size to download', () => {
    const missing = component({ version: '37.1.11', sizeBytes: 441_000_000, localSdk: true })
    expect(componentDetail(missing)).toEqual({
      version: '37.1.11',
      sizeBytes: 441_000_000,
      localSdk: false,
      testPackage: false,
    })
  })

  it('an added root is recognised whatever the spelling', () => {
    expect(isRootAdded(['E:/emu-tmp/m2-e2e/root1'], 'e:\\emu-tmp\\m2-e2e\\root1\\')).toBe(true)
    expect(isRootAdded(['E:/emu-tmp/m2-e2e/root1'], 'E:\\emu-tmp\\m2-e2e\\root2')).toBe(false)
    expect(isRootAdded([], 'E:\\a')).toBe(false)
  })
})

describe('test package', () => {
  it('a self-built emulator from the test package is ready and marked', () => {
    const item = component({ installed: true, version: '37.2.10', testPackage: true, sizeBytes: 0 })
    expect(componentState(item)).toBe('ready')
    expect(componentDetail(item)).toEqual({
      version: '37.2.10',
      sizeBytes: null,
      localSdk: false,
      testPackage: true,
    })
  })

  it('missing or official emulator needs the test package, never a download size', () => {
    const official = component({ version: '37.1.11', needsTestPackage: true, sizeBytes: 0 })
    expect(componentState(official)).toBe('needsPackage')
    expect(componentDetail(official).sizeBytes).toBeNull()
    const none = component({ version: '', needsTestPackage: true, sizeBytes: 0 })
    expect(componentState(none)).toBe('needsPackage')
  })
})
