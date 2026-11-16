import { isDevelopmentEnvironment as isDev } from '@/utils/environment'
import type {
  AnalyticsContext,
  AnalyticsCountBucket,
  AnalyticsDurationBucket,
  AnalyticsEventProps,
  AnalyticsOperationName,
  AnalyticsScriptType,
  RendererAnalyticsEvent,
} from '@/types/analytics'

export function analyticsCountBucket(count: number): AnalyticsCountBucket {
  return count <= 0 ? '0' : count === 1 ? '1' : count <= 5 ? '2-5' : count <= 20 ? '6-20' : '20+'
}

/** 在异步操作开始前取得主进程代次；开发和纯浏览器环境不采集。 */
export function captureAnalyticsContext(): Promise<AnalyticsContext> {
  if (isDev || !window.electronAPI?.analytics) return Promise.resolve(null)
  try {
    return window.electronAPI.analytics.getContext().catch(() => null)
  } catch {
    return Promise.resolve(null)
  }
}

export function recordRendererReady(context: Promise<AnalyticsContext>, durationMs: number): void {
  if (!Number.isFinite(durationMs) || durationMs < 0) return
  recordAnalyticsEvent(context, {
    name: 'renderer_ready',
    props: {
      duration_bucket: durationBucket(durationMs),
      visibility: document.visibilityState === 'hidden' ? 'hidden' : 'visible',
    },
  })
}

export function durationBucket(durationMs: number): AnalyticsDurationBucket {
  return durationMs < 1_000
    ? '<1s'
    : durationMs < 5_000
      ? '1-5s'
      : durationMs < 30_000
        ? '5-30s'
        : durationMs < 120_000
          ? '30-120s'
          : '>120s'
}

export function recordAnalyticsEvent(
  context: Promise<AnalyticsContext>,
  event: RendererAnalyticsEvent
): void {
  void context
    .then(generation => {
      if (generation !== null) {
        window.electronAPI?.analytics?.trackEvent(generation, event)
      }
    })
    .catch(() => {
      // IPC 不可用或窗口关闭不能影响启动。
    })
}

/** 操作只消费一次终态；异步 IPC 不进入业务 await 链。 */
export function beginAnalyticsOperation<K extends AnalyticsOperationName>(
  name: K,
  context = captureAnalyticsContext()
) {
  const startedAt = performance.now()
  let finished = false
  return {
    finish(props: Omit<AnalyticsEventProps[K], 'duration_bucket'>): void {
      if (finished) return
      finished = true
      recordAnalyticsEvent(context, {
        name,
        props: { ...props, duration_bucket: durationBucket(performance.now() - startedAt) },
      } as unknown as RendererAnalyticsEvent)
    },
  }
}

const scriptTypes = new Set([
  'MAA',
  'SRC',
  'MaaEnd',
  'HSR',
  'General',
  'BAAH',
  'MaaFW',
  'M9A',
  'MSS',
  'BetterGI',
  'Okww',
  'OkNte',
  'ZzzOd',
  'Whimbox',
])
const scriptTypeCache = new Map<string, AnalyticsScriptType>()

export function analyticsScriptType(type: unknown): AnalyticsScriptType {
  return typeof type === 'string' && scriptTypes.has(type)
    ? (type as AnalyticsScriptType)
    : 'unknown'
}

/** ID 仅在当前 renderer 的有界内存中关联内置类型，从不放进事件。 */
export function rememberAnalyticsScriptType(id: string, type: unknown): void {
  if (!scriptTypeCache.has(id) && scriptTypeCache.size >= 128)
    scriptTypeCache.delete(scriptTypeCache.keys().next().value!)
  scriptTypeCache.set(id, analyticsScriptType(type))
}

export function getAnalyticsScriptType(id: string): AnalyticsScriptType {
  return scriptTypeCache.get(id) ?? 'unknown'
}

export function analyticsConfigSection(
  data: object
): AnalyticsEventProps['config_write_finished']['section_kind'] {
  const keys = Object.keys(data)
  if (keys.length > 1) return 'multiple'
  const sections: Record<string, AnalyticsEventProps['config_write_finished']['section_kind']> = {
    Info: 'info',
    Function: 'function',
    Notify: 'notify',
    Script: 'script',
    User: 'user',
    UI: 'ui',
  }
  return sections[keys[0] ?? ''] ?? 'other'
}
