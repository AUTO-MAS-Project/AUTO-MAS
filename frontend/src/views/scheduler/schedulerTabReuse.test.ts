import { describe, expect, it } from 'vitest'
import type { SchedulerStatus, SchedulerTab } from './schedulerConstants'
import { findReusableSchedulerTab } from './schedulerTabReuse'

const tab = (
  key: string,
  selectedTaskId: string | null,
  status: SchedulerStatus = '结束',
  taskId: string | null = null
): SchedulerTab => ({
  key,
  title: key,
  closable: key !== 'main',
  status,
  selectedTaskId,
  selectedMode: null,
  taskId,
  logBuffer: '',
  lastLogContent: '',
})

describe('findReusableSchedulerTab', () => {
  it('复用选了同一队列且已结束的调度台', () => {
    const tabs = [tab('main', null, '空闲'), tab('tab-2', 'q1'), tab('tab-3', 'q2')]
    expect(findReusableSchedulerTab(tabs, 'q2')?.key).toBe('tab-3')
  })

  it('空闲与异常结束的调度台也可以复用', () => {
    expect(findReusableSchedulerTab([tab('tab-2', 'q1', '空闲')], 'q1')?.key).toBe('tab-2')
    expect(findReusableSchedulerTab([tab('tab-2', 'q1', '异常')], 'q1')?.key).toBe('tab-2')
  })

  it('不复用正在运行或仍挂着任务的调度台', () => {
    expect(findReusableSchedulerTab([tab('tab-2', 'q1', '运行', 'run-1')], 'q1')).toBeUndefined()
    expect(findReusableSchedulerTab([tab('tab-2', 'q1', '结束', 'run-1')], 'q1')).toBeUndefined()
  })

  it('不复用主调度台', () => {
    expect(findReusableSchedulerTab([tab('main', 'q1', '空闲')], 'q1')).toBeUndefined()
  })

  it('选的任务项不同或没有任务项时不复用', () => {
    const tabs = [tab('tab-2', 'q1'), tab('tab-3', null)]
    expect(findReusableSchedulerTab(tabs, 'q2')).toBeUndefined()
    expect(findReusableSchedulerTab(tabs, undefined)).toBeUndefined()
    expect(findReusableSchedulerTab(tabs, null)).toBeUndefined()
  })

  it('跳过手动启动还没返回的调度台', () => {
    const tabs = [tab('tab-2', 'q1', '空闲'), tab('tab-3', 'q1')]
    expect(findReusableSchedulerTab(tabs, 'q1', new Set(['tab-2']))?.key).toBe('tab-3')
    expect(findReusableSchedulerTab(tabs, 'q1', new Set(['tab-2', 'tab-3']))).toBeUndefined()
  })

  it('有多个可复用时取最早的那个', () => {
    const tabs = [tab('tab-2', 'q1'), tab('tab-5', 'q1')]
    expect(findReusableSchedulerTab(tabs, 'q1')?.key).toBe('tab-2')
  })
})
