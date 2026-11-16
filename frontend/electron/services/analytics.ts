import { randomInt } from 'crypto'
import type {
  AnalyticsContext,
  AnalyticsEvent,
  AnalyticsEventName,
  AnalyticsEventProps,
} from '../../src/types/analytics'
import { validateAnalyticsEvent } from './analyticsPolicy'

const REQUEST_TIMEOUT_MS = 5_000
const SESSION_IDLE_MS = 60 * 60 * 1_000
const SESSION_MAX_AGE_MS = 24 * SESSION_IDLE_MS

export interface AnalyticsPayload {
  timestamp: string
  sessionId: string
  eventName: AnalyticsEventName
  systemProps: {
    isDebug: false
    locale: string
    osName: string
    osVersion: string
    engineName: string
    engineVersion: string
    appVersion: string
    sdkVersion: string
  }
  props: Record<string, string>
}

interface AnalyticsOptions {
  isAllowed(): boolean
  systemProps(): AnalyticsPayload['systemProps']
  send(payload: AnalyticsPayload, signal: AbortSignal): Promise<void>
}

/** 主进程汇聚采集；有界并发与限频，不缓冲、不重试、不落盘。 */
export class AnalyticsService {
  private enabled = false
  private disposed = false
  private generation = 0
  private readonly emitted = new Set<AnalyticsPayload['eventName']>()
  private readonly requests = new Set<AbortController>()
  private session: { id: string; startedAt: number; touchedAt: number } | null = null
  private minute = 0
  private minuteCount = 0
  private readonly eventCounts = new Map<AnalyticsEventName, number>()
  private lastScreen = ''
  private automaticUpdateCheckEmitted = false

  constructor(private readonly options: AnalyticsOptions) {}

  setEnabled(enabled: boolean): void {
    if (this.disposed || this.enabled === enabled) return
    this.enabled = enabled
    this.generation++
    this.session = null
    this.lastScreen = ''
    for (const request of this.requests) request.abort()
    this.requests.clear()
  }

  getContext(): AnalyticsContext {
    try {
      return !this.disposed && this.enabled && this.options.isAllowed() ? this.generation : null
    } catch {
      return null
    }
  }

  recordAppStarted(
    props: AnalyticsEventProps['app_started'] = {
      launch_kind: 'unknown',
      runtime_mode: 'unknown',
      release_channel: 'unknown',
    }
  ): void {
    this.emit('app_started', props, this.getContext())
  }

  recordRendererEvent(context: unknown, event: unknown): void {
    if (context !== this.getContext() || typeof context !== 'number') return
    const valid = validateAnalyticsEvent(event, true)
    if (valid) this.emit(valid.name, valid.props, context)
  }

  recordMainEvent(context: AnalyticsContext, event: AnalyticsEvent): void {
    const valid = validateAnalyticsEvent(event, false)
    if (valid) this.emit(valid.name, valid.props, context)
  }

  dispose(): void {
    this.setEnabled(false)
    this.disposed = true
  }

  private emit(
    name: AnalyticsPayload['eventName'],
    props: Record<string, string>,
    context: AnalyticsContext
  ): void {
    try {
      this.emitAllowed(name, props, context)
    } catch {
      // 系统信息或采集实现异常也不能抛回业务调用方。
    }
  }

  private emitAllowed(
    name: AnalyticsPayload['eventName'],
    props: Record<string, string>,
    context: AnalyticsContext
  ): void {
    if (context === null || context !== this.getContext()) return
    const once =
      name === 'app_started' || name === 'renderer_ready' || name === 'initialization_decided'
    if (once && this.emitted.has(name)) return
    const automaticCheck = name === 'update_check_finished' && props.trigger_kind === 'automatic'
    if (automaticCheck && this.automaticUpdateCheckEmitted) return
    const now = Date.now()
    const minute = Math.floor(now / 60_000)
    if (minute !== this.minute) {
      this.minute = minute
      this.minuteCount = 0
      this.eventCounts.clear()
    }
    // 成功保存独立随机抽样；未入样的调用不占事件族预算。
    const sampleRate = name === 'config_write_finished' && props.outcome === 'success' ? 10 : 1
    if (sampleRate === 10 && randomInt(sampleRate) !== 0) return
    const count = (this.eventCounts.get(name) ?? 0) + 1
    this.eventCounts.set(name, count)
    if (this.minuteCount >= 120 || count > 60 || this.requests.size >= 4) return
    if (name === 'screen_view') {
      const key = `${props.screen}:${props.script_type}`
      if (this.lastScreen === key) return
      this.lastScreen = key
    }
    if (once) this.emitted.add(name)
    if (automaticCheck) this.automaticUpdateCheckEmitted = true
    this.minuteCount++
    if (
      !this.session ||
      now - this.session.touchedAt >= SESSION_IDLE_MS ||
      now - this.session.startedAt >= SESSION_MAX_AGE_MS ||
      now < this.session.touchedAt
    ) {
      this.session = {
        id: `${Math.floor(now / 1_000)}${randomInt(100_000_000).toString().padStart(8, '0')}`,
        startedAt: now,
        touchedAt: now,
      }
    }
    this.session.touchedAt = now
    const payload: AnalyticsPayload = {
      timestamp: new Date(now).toISOString(),
      sessionId: this.session.id,
      eventName: name,
      systemProps: this.options.systemProps(),
      props:
        name === 'config_write_finished' ? { ...props, sample_rate: String(sampleRate) } : props,
    }
    const controller = new AbortController()
    this.requests.add(controller)
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
    timeout.unref()
    // 发送放在业务调用之后；微任务执行前再次检查代次，关闭期间不留下补发项。
    void Promise.resolve()
      .then(() => {
        if (!controller.signal.aborted && context === this.getContext()) {
          return this.options.send(payload, controller.signal)
        }
      })
      .catch(() => {
        // 断网、拒收与超时均静默丢弃，不能改变业务结果或递归生成诊断事件。
      })
      .finally(() => {
        clearTimeout(timeout)
        this.requests.delete(controller)
      })
  }
}
