import { describe, expect, it } from 'vitest'

import type { Emulator2AvdComponentItem, Emulator2AvdInstanceOptionsOut } from '@/api'
import {
  DEFAULT_MEMORY_MB,
  componentDetail,
  componentState,
  createOptions,
  defaultAvdOptions,
  hasBlockingFailure,
  isRootAdded,
  markModAvdOptions,
  optionsChanges,
  optionsFromOut,
  precheckLevel,
  samePath,
} from './avdLogic'

const component = (over: Partial<Emulator2AvdComponentItem>): Emulator2AvdComponentItem => ({
  id: 'emulator',
  name: 'Android Emulator',
  installed: false,
  ...over,
})

describe('instance options', () => {
  it('defaults follow the user-decided values', () => {
    expect(defaultAvdOptions()).toEqual({ memoryMb: 6144, balloon: true })
    expect(DEFAULT_MEMORY_MB).toBe(6144)
  })

  it('reads the instance memory as is', () => {
    const out: Emulator2AvdInstanceOptionsOut = { memoryMb: 4096, balloon: false }
    expect(optionsFromOut(out)).toEqual({ memoryMb: 4096, balloon: false })
    expect(optionsFromOut({ ...out, balloon: undefined }).balloon).toBe(true)
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

  it('create sends memory and balloon only (display and sound are fixed)', () => {
    expect(createOptions(defaultAvdOptions())).toEqual({ memoryMb: 6144, balloon: true })
    expect(createOptions({ memoryMb: 4096, balloon: false })).toEqual({
      memoryMb: 4096,
      balloon: false,
    })
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
    expect(hasBlockingFailure([{ id: 'components', title: '', ok: false, blocking: true }])).toBe(
      true
    )
    expect(hasBlockingFailure(undefined)).toBe(false)
  })
})

describe('components', () => {
  it('compares Windows roots loosely', () => {
    expect(samePath('E:\\emu-tmp\\root1\\', 'e:/emu-tmp/root1')).toBe(true)
    expect(samePath('E:\\a', 'E:\\b')).toBe(false)
    expect(samePath('', 'E:\\a')).toBe(false)
  })

  it('component state', () => {
    expect(componentState(component({ installed: true }))).toBe('ready')
    expect(componentState(component({ needsTestPackage: true }))).toBe('needsPackage')
    expect(componentState(component({}))).toBe('missing')
  })

  it('ready components show the installed version; local SDK is marked', () => {
    const local = component({ installed: true, version: '37.2.10', localSdk: true })
    expect(componentDetail(local)).toEqual({
      version: '37.2.10',
      localSdk: true,
      testPackage: false,
      build: '',
      outdated: false,
    })
  })

  it('missing components never claim a source', () => {
    const missing = component({ version: '', localSdk: true, testPackage: true })
    expect(componentDetail(missing)).toMatchObject({ localSdk: false, testPackage: false })
  })

  it('an added root is recognised whatever the spelling', () => {
    expect(isRootAdded(['E:/emu-tmp/m2-e2e/root1'], 'e:\\emu-tmp\\m2-e2e\\root1\\')).toBe(true)
    expect(isRootAdded(['E:/emu-tmp/m2-e2e/root1'], 'E:\\emu-tmp\\m2-e2e\\root2')).toBe(false)
    expect(isRootAdded([], 'E:\\a')).toBe(false)
  })
})

describe('test package', () => {
  it('a self-built emulator from the test package is ready and marked', () => {
    const item = component({
      installed: true,
      version: '37.2.10',
      testPackage: true,
      build: 'mas-25',
    })
    expect(componentState(item)).toBe('ready')
    expect(componentDetail(item)).toEqual({
      version: '37.2.10',
      localSdk: false,
      testPackage: true,
      build: 'mas-25',
      outdated: false,
    })
  })

  it('an outdated test package needs a new package and carries its build', () => {
    const old = component({
      version: '37.2.10',
      needsTestPackage: true,
      outdatedTestPackage: true,
      build: 'mas-24',
    })
    expect(componentState(old)).toBe('needsPackage')
    expect(componentDetail(old)).toMatchObject({ build: 'mas-24', outdated: true })
  })
})

describe('mod AVD is M9A only', () => {
  const options = [
    { label: 'MuMu 0', value: 'mumu:0' },
    { label: 'mas_1', value: 'avd:1' },
  ]
  const isAvd = (value: string | null) => Boolean(value?.startsWith('avd:'))

  it('greys out mod AVD devices for other scripts and says why', () => {
    expect(markModAvdOptions(options, isAvd, false, '只支持 M9A')).toEqual([
      { label: 'MuMu 0', value: 'mumu:0' },
      { label: 'mas_1（只支持 M9A）', value: 'avd:1', disabled: true },
    ])
  })

  it('leaves the list untouched for M9A', () => {
    expect(markModAvdOptions(options, isAvd, true, '只支持 M9A')).toBe(options)
  })
})
