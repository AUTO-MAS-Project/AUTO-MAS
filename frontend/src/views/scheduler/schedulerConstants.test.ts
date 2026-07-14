import { describe, expect, it } from 'vitest'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { getTaskModeOptions } from './schedulerConstants'

describe('getTaskModeOptions', () => {
  it('keeps the generic scheduler modes for queue items', () => {
    expect(getTaskModeOptions(null).map(option => option.value)).toEqual([
      TaskCreateIn.mode.AUTO_PROXY,
      TaskCreateIn.mode.MANUAL_REVIEW,
    ])
  })

  it('hides ManualReview when the selected script only supports AutoProxy', () => {
    expect(getTaskModeOptions(['AutoProxy']).map(option => option.value)).toEqual([
      TaskCreateIn.mode.AUTO_PROXY,
    ])
  })

  it('returns no scheduler mode for an explicitly empty capability', () => {
    expect(getTaskModeOptions([])).toEqual([])
  })
})
