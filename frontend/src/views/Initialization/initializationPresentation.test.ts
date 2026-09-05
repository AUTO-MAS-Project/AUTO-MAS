import { describe, expect, it } from 'vitest'
import {
  formatElapsedSeconds,
  getInitializationStageKey,
  getInitializationStageStatus,
} from './initializationPresentation'

describe('初始化界面展示模型', () => {
  it('把旧环境准备步骤合并成一个用户可理解的阶段', () => {
    expect(getInitializationStageKey('python')).toBe('environment')
    expect(getInitializationStageKey('pip')).toBe('environment')
    expect(getInitializationStageKey('git')).toBe('environment')
    expect(getInitializationStageKey('repository')).toBe('repository')
  })

  it('聚合阶段状态时优先展示失败和处理中', () => {
    expect(
      getInitializationStageStatus('environment', {
        python: 'success',
        pip: 'failed',
        git: 'processing',
      })
    ).toBe('failed')

    expect(
      getInitializationStageStatus('environment', {
        python: 'success',
        pip: 'processing',
        git: 'waiting',
      })
    ).toBe('processing')

    expect(
      getInitializationStageStatus('environment', {
        python: 'success',
        pip: 'success',
        git: 'success',
      })
    ).toBe('success')
  })

  it('把等待时间格式化为稳定的分秒显示', () => {
    expect(formatElapsedSeconds(0)).toBe('00:00')
    expect(formatElapsedSeconds(65)).toBe('01:05')
    expect(formatElapsedSeconds(-1)).toBe('00:00')
  })
})
