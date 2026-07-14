import { describe, expect, it } from 'vitest'

import { deepMergeRecord } from './deepMerge'

describe('deepMergeRecord', () => {
  it('merges plugin form patches without replacing sibling fields', () => {
    const current = {
      Info: { Name: '测试', Controller: 'ADB' },
      Task: { SelectedPreset: 'Default', Enabled: true },
    }

    expect(
      deepMergeRecord(current, {
        Info: { Controller: 'Desktop' },
        Task: { SelectedPreset: 'Daily', TaskSnapshot: 'snapshot' },
      })
    ).toEqual({
      Info: { Name: '测试', Controller: 'Desktop' },
      Task: { SelectedPreset: 'Daily', Enabled: true, TaskSnapshot: 'snapshot' },
    })
  })
})
