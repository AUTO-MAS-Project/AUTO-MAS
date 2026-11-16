import { beginAnalyticsOperation } from './analytics'
import type { AnalyticsEventProps, RendererAnalyticsEventName } from '@/types/analytics'
import type {
  FeatureAnalyticsEventName,
  FeatureAnalyticsOutcome,
} from '../../electron/services/analyticsFeaturePolicy'

type RendererFeature = Extract<FeatureAnalyticsEventName, RendererAnalyticsEventName>

/** 显式业务边界旁观一次响应，保留原 Promise（含取消能力），不增加请求或等待。 */
export function observeFeature<K extends RendererFeature, P extends PromiseLike<unknown>>(
  name: K,
  props: Omit<AnalyticsEventProps[K], 'outcome' | 'duration_bucket'>,
  run: () => P,
  outcome: (
    result: Awaited<P>
  ) =>
    | FeatureAnalyticsOutcome
    | ({ outcome: FeatureAnalyticsOutcome } & Partial<
        Omit<AnalyticsEventProps[K], 'duration_bucket'>
      >)
): P {
  const operation = beginAnalyticsOperation(name)
  const finish = (result: FeatureAnalyticsOutcome) => {
    operation.finish({ ...props, outcome: result } as Omit<
      AnalyticsEventProps[K],
      'duration_bucket'
    >)
  }
  try {
    const request = run()
    void Promise.resolve(request).then(
      result => {
        try {
          const observed = outcome(result as Awaited<P>)
          if (typeof observed === 'string') finish(observed)
          else
            operation.finish({ ...props, ...observed } as Omit<
              AnalyticsEventProps[K],
              'duration_bucket'
            >)
        } catch {
          finish('unknown')
        }
      },
      () => finish('unknown')
    )
    return request
  } catch (error) {
    finish('unknown')
    throw error
  }
}

export const apiOutcome = (result: { code?: number }) =>
  result.code === 200
    ? ('success' as const)
    : result.code === 409
      ? ('blocked' as const)
      : ('failure' as const)

export const commandOutcome = (result: {
  success: boolean
  cancelled?: boolean
  canceled?: boolean
}) =>
  result.cancelled || result.canceled
    ? ('cancelled' as const)
    : result.success
      ? ('success' as const)
      : ('failure' as const)
