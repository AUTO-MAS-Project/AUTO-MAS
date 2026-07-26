import { describe, expect, it } from 'vitest'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import { buildSchedulerTaskOptions } from './schedulerTaskOptions'

describe('buildSchedulerTaskOptions', () => {
  it('保留同前缀脚本的完整真实名称并保持任务 ID 不变', () => {
    const source: ComboBoxItem[] = [
      {
        label: '脚本 - MAA - 博士主账号日常',
        value: 'script-main',
        supported_modes: ['AutoProxy'],
      },
      {
        label: '脚本 - MAA - 博士副账号日常',
        value: 'script-alt',
        supported_modes: ['ManualReview'],
      },
    ]

    const options = buildSchedulerTaskOptions(source)

    expect(options.map(option => option.label)).toEqual([
      '脚本 - MAA - 博士主账号日常',
      '脚本 - MAA - 博士副账号日常',
    ])
    expect(new Set(options.map(option => option.label)).size).toBe(2)
    expect(options.map(option => option.value)).toEqual(['script-main', 'script-alt'])
    expect(options.map(option => option.title)).toEqual(options.map(option => option.label))
    expect(options.map(option => option.supported_modes)).toEqual([['AutoProxy'], ['ManualReview']])
  })

  it('保留队列名称和未选择项的空 value', () => {
    const options = buildSchedulerTaskOptions([
      { label: '未选择', value: null },
      { label: '队列 - 夜间多账号任务', value: 'queue-night' },
    ])

    expect(options).toEqual([
      { label: '未选择', value: null, title: '未选择' },
      {
        label: '队列 - 夜间多账号任务',
        value: 'queue-night',
        title: '队列 - 夜间多账号任务',
      },
    ])
  })
})
