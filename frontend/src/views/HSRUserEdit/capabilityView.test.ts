import { describe, expect, it } from 'vitest'
import type { HSREngine, HSRCapabilitySnapshot } from '@/composables/useHSRPluginApi'
import { buildHSRCapabilityView, resolveCapabilityTaskEngine } from './capabilityView'

const TASKS = [
  { key: 'Daily', name: '日常', phase: 'daily', description: '', engines: ['SRA', 'M7A'] },
  {
    key: 'ForgottenHall',
    name: '三深渊',
    phase: 'monthly',
    description: '',
    engines: ['M7A'],
  },
] as HSRCapabilitySnapshot['tasks']

const snapshot = (
  effectiveEngines: HSREngine[],
  supportedModes: string[] = []
): HSRCapabilitySnapshot => ({
  revision: 1,
  available: effectiveEngines.length > 0,
  unavailable_reason: effectiveEngines.length ? null : '缺少适配器',
  candidate_engines: [...effectiveEngines],
  selected_engines: [...effectiveEngines],
  effective_engines: [...effectiveEngines],
  supported_modes: supportedModes,
  adapters: [],
  tasks: TASKS,
  warnings: [],
})

describe('HSR capability-driven editor view', () => {
  it('disables all engine surfaces when no adapter is effective', () => {
    const view = buildHSRCapabilityView(snapshot([]))
    expect(view.available).toBe(false)
    expect(view.showSRAFields).toBe(false)
    expect(view.showM7AFields).toBe(false)
    expect(view.showTaskMapping).toBe(false)
    expect(view.taskKeys.size).toBe(0)
  })

  it('shows only SRA fields and common SRA tasks for SRA-only', () => {
    const current = snapshot(['SRA'], ['AutoProxy', 'ManualReview'])
    const view = buildHSRCapabilityView(current)
    expect(view.showSRAFields).toBe(true)
    expect(view.showM7AFields).toBe(false)
    expect(view.showTaskMapping).toBe(false)
    expect(view.supportedModes.has('ManualReview')).toBe(true)
    expect(view.taskKeys.has('ForgottenHall')).toBe(false)
    expect(resolveCapabilityTaskEngine(current, 'Daily', 'M7A')).toBe('SRA')
  })

  it('shows only M7A fields and never exposes ManualReview for M7A-only', () => {
    const current = snapshot(['M7A'], ['AutoProxy'])
    const view = buildHSRCapabilityView(current)
    expect(view.showSRAFields).toBe(false)
    expect(view.showM7AFields).toBe(true)
    expect(view.showTaskMapping).toBe(false)
    expect(view.supportedModes.has('ManualReview')).toBe(false)
    expect(view.taskKeys.has('ForgottenHall')).toBe(true)
    expect(resolveCapabilityTaskEngine(current, 'Daily', 'SRA')).toBe('M7A')
  })

  it('shows the aggregate and honors valid task mapping for both engines', () => {
    const current = snapshot(['SRA', 'M7A'], ['AutoProxy', 'ManualReview'])
    const view = buildHSRCapabilityView(current)
    expect(view.showSRAFields).toBe(true)
    expect(view.showM7AFields).toBe(true)
    expect(view.showTaskMapping).toBe(true)
    expect(resolveCapabilityTaskEngine(current, 'Daily', 'M7A')).toBe('M7A')
    expect(resolveCapabilityTaskEngine(current, 'ForgottenHall', 'SRA')).toBe('M7A')
  })
})
