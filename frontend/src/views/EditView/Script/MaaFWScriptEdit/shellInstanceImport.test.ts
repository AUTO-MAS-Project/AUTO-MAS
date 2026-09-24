import { describe, expect, it } from 'vitest'
import type { MaaFWShellInstanceImportItem } from '@/api'
import {
  buildShellImportReportLines,
  describeShellSources,
  summarizeShellImport,
  truncateItems,
} from './shellInstanceImport'

const item = (patch: Partial<MaaFWShellInstanceImportItem>): MaaFWShellInstanceImportItem => ({
  instanceId: 'mfaa:x',
  instanceName: '配置',
  success: true,
  userId: 'u1',
  name: '配置',
  importedTaskCount: 1,
  skipped: [],
  error: '',
  ...patch,
})

// 把 key 与参数原样拼出来，断言只看选了哪条文案、带了哪些参数
const t = (key: string, named?: Record<string, unknown>) =>
  named ? `${key}${JSON.stringify(named)}` : key

describe('summarizeShellImport', () => {
  it('按建成 / 失败 / 导不全分开', () => {
    const summary = summarizeShellImport([
      item({ instanceId: 'a' }),
      item({ instanceId: 'b', skipped: ['任务「X」'] }),
      item({ instanceId: 'c', success: false, userId: '', error: '找不到' }),
    ])
    expect(summary.created.map(i => i.instanceId)).toEqual(['a', 'b'])
    expect(summary.partial.map(i => i.instanceId)).toEqual(['b'])
    expect(summary.failed.map(i => i.instanceId)).toEqual(['c'])
  })

  it('success 为真但没有 userId 的也算失败', () => {
    const summary = summarizeShellImport([item({ userId: '' })])
    expect(summary.created).toEqual([])
    expect(summary.failed).toHaveLength(1)
  })
})

describe('truncateItems', () => {
  it('不超过上限原样给出', () => {
    expect(truncateItems(['a', 'b'], 5)).toEqual({ shown: ['a', 'b'], rest: 0 })
  })

  it('超过上限只留前几项并给出省掉的项数', () => {
    expect(truncateItems(['a', 'b', 'c', 'd'], 2)).toEqual({ shown: ['a', 'b'], rest: 2 })
  })
})

describe('describeShellSources', () => {
  it('去重并保持出现顺序', () => {
    expect(describeShellSources(['MFAAvalonia', 'MXU', 'MFAAvalonia'])).toBe('MFAAvalonia / MXU')
    expect(describeShellSources(['MXU'])).toBe('MXU')
  })
})

describe('buildShellImportReportLines', () => {
  it('没有失败也没有跳过时不出提示', () => {
    expect(buildShellImportReportLines(summarizeShellImport([item({})]), t)).toEqual([])
  })

  it('失败的实例写在前面，导不全的写在后面', () => {
    const lines = buildShellImportReportLines(
      summarizeShellImport([
        item({ name: '甲', skipped: ['任务「X」'] }),
        item({ instanceId: 'b', instanceName: '乙', success: false, userId: '', error: '被拒' }),
      ]),
      t
    )
    expect(lines).toEqual([
      'edit.shellImportFailedHead{"count":1}',
      'edit.shellImportFailedLine{"name":"乙","reason":"被拒"}',
      'edit.shellImportSkippedLine{"name":"甲","count":1,"items":"任务「X」"}',
    ])
  })

  it('跳过的项太多时截断并给出总数', () => {
    const skipped = ['1', '2', '3', '4', '5', '6', '7']
    const [line] = buildShellImportReportLines(
      summarizeShellImport([item({ name: '甲', skipped })]),
      t
    )
    expect(line).toBe(
      'edit.shellImportSkippedLineMore{"name":"甲","count":7,"items":"1edit.shellImportListSeparator2edit.shellImportListSeparator3edit.shellImportListSeparator4edit.shellImportListSeparator5","rest":2}'
    )
  })

  it('找不到的实例没有实例名时用实例 ID', () => {
    const lines = buildShellImportReportLines(
      summarizeShellImport([
        item({ instanceId: 'mfaa:gone', instanceName: '', success: false, userId: '', error: '' }),
      ]),
      t
    )
    expect(lines[1]).toBe('edit.shellImportFailedLine{"name":"mfaa:gone","reason":"-"}')
  })
})
