import { describe, expect, it } from 'vitest'
import type { WSMaaFWProjectUpdateProgressData } from '@/services/websocket/types'
import {
  MAX_UPDATE_LOG_LINES,
  createUpdateProgressState,
  finishUpdateProgress,
  formatAppliedFiles,
  formatDownloadSize,
  formatDownloadSpeed,
  progressBarPercent,
  reduceUpdateProgress,
} from './updateProgress'

const event = (
  partial: Partial<WSMaaFWProjectUpdateProgressData> & { stage: string }
): WSMaaFWProjectUpdateProgressData => ({ status: 'running', message: '', ...partial })

describe('reduceUpdateProgress', () => {
  it('日志事件只追加日志行，不动阶段', () => {
    const state = reduceUpdateProgress(
      createUpdateProgressState('checking'),
      event({ stage: 'log', log: 'start checking', message: 'start checking' })
    )
    expect(state.phase).toBe('checking')
    expect(state.logs).toEqual(['start checking'])
    expect(state.message).toBe('')
  })

  it('日志框只留最后 MAX_UPDATE_LOG_LINES 行', () => {
    let state = createUpdateProgressState('checking')
    for (let i = 0; i < MAX_UPDATE_LOG_LINES + 5; i += 1) {
      state = reduceUpdateProgress(state, event({ stage: 'log', log: `line ${i}` }))
    }
    expect(state.logs).toHaveLength(MAX_UPDATE_LOG_LINES)
    expect(state.logs[0]).toBe('line 5')
  })

  it('下载事件带上字节、速度与百分比，包类型一路继承', () => {
    let state = reduceUpdateProgress(
      createUpdateProgressState('checking'),
      event({ stage: 'checking', message: '发现新版本 v2', packageKind: 'incremental' })
    )
    state = reduceUpdateProgress(
      state,
      event({
        stage: 'downloading',
        percent: 45.5,
        downloadedBytes: 12 * 1024 * 1024,
        totalBytes: 50 * 1024 * 1024,
        speedBytesPerSec: 3355443,
      })
    )
    expect(state.phase).toBe('downloading')
    expect(state.packageKind).toBe('incremental')
    expect(formatDownloadSize(state)).toBe('12 MB / 50 MB')
    expect(formatDownloadSpeed(state)).toBe('3.2 MB/s')
    expect(progressBarPercent(state)).toBe(46)
  })

  it('覆盖阶段显示 n/m，plan_validated 的 full 覆盖之前的包类型', () => {
    let state = reduceUpdateProgress(
      createUpdateProgressState('downloading'),
      event({ stage: 'plan_validated', packageKind: 'full' })
    )
    expect(state.phase).toBe('preparing')
    expect(state.packageKind).toBe('full')
    state = reduceUpdateProgress(
      state,
      event({ stage: 'applying', percent: 26.7, appliedFiles: 120, totalFiles: 450 })
    )
    expect(state.phase).toBe('applying')
    expect(formatAppliedFiles(state)).toBe('120/450')
    expect(progressBarPercent(state)).toBe(27)
  })

  it('status=failed 一律进失败态，之后迟到的 running 事件不再翻回去', () => {
    let state = reduceUpdateProgress(
      createUpdateProgressState('downloading'),
      event({ stage: 'failed', status: 'failed', message: '下载失败' })
    )
    expect(state.phase).toBe('failed')
    state = reduceUpdateProgress(
      state,
      event({ stage: 'downloading', percent: 99, log: '迟到的一行' })
    )
    expect(state.phase).toBe('failed')
    expect(state.message).toBe('下载失败')
    expect(state.logs).toEqual(['迟到的一行'])
  })

  it('rolled_back 与 completed 都是终态', () => {
    const rolled = reduceUpdateProgress(
      createUpdateProgressState('applying'),
      event({ stage: 'rolled_back', message: '已回滚' })
    )
    expect(rolled.phase).toBe('rolled_back')
    const done = reduceUpdateProgress(
      createUpdateProgressState('validating'),
      event({ stage: 'completed', status: 'success', message: '更新完成' })
    )
    expect(done.phase).toBe('completed')
    expect(done.percent).toBe(100)
  })

  it('未知阶段名保持原阶段，只更新文案', () => {
    const state = reduceUpdateProgress(
      createUpdateProgressState('checking'),
      event({ stage: 'something_new', message: '新阶段' })
    )
    expect(state.phase).toBe('checking')
    expect(state.message).toBe('新阶段')
  })
})

describe('finishUpdateProgress', () => {
  it('HTTP 响应兜底收尾，但不覆盖 WS 已给的终态', () => {
    const running = createUpdateProgressState('checking')
    expect(finishUpdateProgress(running, { success: true, message: '已是最新' }).phase).toBe(
      'completed'
    )
    expect(finishUpdateProgress(running, { success: false, message: '失败' }).phase).toBe('failed')
    const failed = { ...createUpdateProgressState('failed'), message: '后端那句' }
    expect(finishUpdateProgress(failed, { success: true, message: 'HTTP 那句' })).toBe(failed)
  })
})

describe('格式化', () => {
  it('总量未知只给已下载量，没有速度采样为空串', () => {
    const state = {
      ...createUpdateProgressState('downloading'),
      downloadedBytes: 1536,
      speedBytesPerSec: null,
    }
    expect(formatDownloadSize(state)).toBe('1.5 KB')
    expect(formatDownloadSpeed(state)).toBe('')
    expect(formatAppliedFiles(state)).toBe('')
  })

  it('非下载 / 覆盖阶段没有进度条', () => {
    expect(progressBarPercent({ ...createUpdateProgressState('checking'), percent: 50 })).toBe(null)
    expect(progressBarPercent(createUpdateProgressState('downloading'))).toBe(null)
  })
})
