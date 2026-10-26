import { beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsEventProps } from '@/types/analytics'
import type { ActivityLoadState, HomeActivitySource } from './useHomeActivitySource'

type Props = AnalyticsEventProps['home_activity_load_finished']
const knownSources = new Set([
  'arknights',
  'endfield',
  'starrail',
  'bluearchive',
  'reverse1999',
  'stellasora',
])
const sraGames = new Set(['genshin', 'zenless', 'wutheringwaves', 'nte', 'infinitynikki'])

export function activityBatchResult(
  states: ActivityLoadState[]
): Pick<Props, 'outcome' | 'cache_kind'> {
  const success = states.filter(state => state.outcome === 'success').length
  const cached = states.some(state => state.cacheUsed)
  return {
    outcome:
      !states.length || states.some(state => state.outcome === 'unknown')
        ? 'unknown'
        : success === states.length
          ? 'success'
          : success || states.some(state => state.available)
            ? 'partial'
            : 'failure',
    cache_kind: cached ? (success ? 'mixed' : 'cache') : 'network',
  }
}

/** 一张游戏卡的多来源/多服务器合为一次结果，自动退避和后台刷新不计数。 */
export function observeHomeActivitySource<
  T extends Pick<HomeActivitySource, 'start' | 'stop' | 'refresh' | 'whenLoaded'>,
>(game: string, source: T): T {
  const source_kind: Props['source_kind'] = knownSources.has(game)
    ? (game as Props['source_kind'])
    : sraGames.has(game)
      ? 'sra'
      : 'unknown'
  let started = false
  const observe = (trigger_kind: 'initial' | 'manual', run: () => void | Promise<void>) => {
    const previousBatch = source.whenLoaded()
    const telemetry = beginAnalyticsOperation('home_activity_load_finished')
    const finish = (states: ActivityLoadState[]) =>
      telemetry.finish({
        source_kind,
        trigger_kind,
        ...activityBatchResult(states),
      })
    const request = run()
    const batch = source.whenLoaded()
    if (batch === previousBatch) return request
    void batch.then(finish, () =>
      telemetry.finish({ source_kind, trigger_kind, cache_kind: 'unknown', outcome: 'unknown' })
    )
    return request
  }
  return {
    ...source,
    start: () => {
      if (started) return source.start()
      started = true
      observe('initial', source.start)
    },
    refresh: () => observe('manual', source.refresh) as Promise<void>,
  }
}
