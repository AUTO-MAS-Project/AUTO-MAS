import { beginAnalyticsOperation, captureAnalyticsContext } from './analytics'
import type { AnalyticsEventProps, AnalyticsUpdateSource } from '@/types/analytics'

const sources: Record<string, AnalyticsUpdateSource> = {
  CNB: 'cnb',
  GitHub: 'github',
  MirrorChyan: 'mirrorchyan',
  AutoSite: 'autosite',
}

export function analyticsUpdateSource(source: string): AnalyticsUpdateSource {
  return Object.prototype.hasOwnProperty.call(sources, source) ? sources[source] : 'unknown'
}

/** 开始与终态共享操作前代次；来源只取首帧或请求返回时已知的内置类别。 */
export function beginDownloadAnalytics(version: string) {
  const context = captureAnalyticsContext()
  const startedOperation = beginAnalyticsOperation('update_download_started', context)
  const finishedOperation = beginAnalyticsOperation('update_download_finished', context)
  const release_channel = /^v?\d+\.\d+\.\d+$/.test(version)
    ? 'stable'
    : /^v?\d+\.\d+\.\d+-beta\.\d+$/.test(version)
      ? 'beta'
      : 'unknown'
  const started = (source: string) =>
    startedOperation.finish({
      source_kind: analyticsUpdateSource(source),
      release_channel,
    })
  return {
    started,
    finish(source: string, outcome: AnalyticsEventProps['update_download_finished']['outcome']) {
      started(source)
      finishedOperation.finish({ source: analyticsUpdateSource(source), outcome })
    },
  }
}
