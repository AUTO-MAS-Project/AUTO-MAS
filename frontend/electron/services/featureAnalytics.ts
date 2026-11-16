import { analyticsService } from './analyticsService'
import { analyticsDuration } from './analyticsPolicy'
import type { AnalyticsEvent, AnalyticsEventProps } from '../../src/types/analytics'
import type { FeatureAnalyticsEventName } from './analyticsFeaturePolicy'

/** 主进程操作先捕获代次；退出、关闭遥测和旧回调不能补造结果。 */
export function beginMainFeature<K extends FeatureAnalyticsEventName>(name: K) {
  const context = analyticsService.getContext()
  const startedAt = performance.now()
  let finished = false
  return {
    finish(props: Omit<AnalyticsEventProps[K], 'duration_bucket'>): void {
      if (finished) return
      finished = true
      analyticsService.recordMainEvent(context, {
        name,
        props: { ...props, duration_bucket: analyticsDuration(performance.now() - startedAt) },
      } as AnalyticsEvent)
    },
  }
}

export function mainCountBucket(count: number): '0' | '1' | '2-5' | '6-20' | '20+' {
  return count <= 0 ? '0' : count === 1 ? '1' : count <= 5 ? '2-5' : count <= 20 ? '6-20' : '20+'
}
