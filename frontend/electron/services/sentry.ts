import { startupAttempt } from './startupHardware/monitor'
import { allowedFields } from './startupHardware/summary'
import * as Sentry from '@sentry/electron/main'
import { app } from 'electron'

import { isDevelopmentEnvironment } from './instanceConfig'
import { sanitizeMainSentryEvent } from './sentryPrivacy'
import type { RendererCrashDetails, RendererReloadResult } from '../rendererCrashRecovery'

const SENTRY_DSN =
  'https://6ad15803ac77e44f24f46f2dfa599def@o4511881138733056.ingest.us.sentry.io/4511902510678016'
const processStartedAt = performance.now()

type MetricAttributes = Record<string, string | number | boolean>

let sentryStarted = false
let telemetryGeneration = 0

const isSentryEnabled = () => Sentry.getClient()?.getOptions().enabled === true

const startSentry = () => {
  if (isDevelopmentEnvironment()) return

  Sentry.init({
    dsn: SENTRY_DSN,
    release: `auto-mas@${app.getVersion()}`,
    environment: 'production',
    sendDefaultPii: false,
    includeLocalVariables: false,
    serverName: 'AUTO-MAS',
    attachScreenshot: false,
    enableRendererProfiling: false,
    // 显式建立 enabled，避免下面的开关判断依赖 SDK 默认值。
    enabled: true,
    // Minidump 以附件形式上传，附件在 beforeSend 之后才拼进 envelope，
    // 脱敏钩子够不到；而 Windows minidump 含完整命令行与环境变量块，故整体禁用。
    integrations: defaultIntegrations =>
      defaultIntegrations.filter(
        integration => integration.name !== 'Console' && !/minidump/i.test(integration.name)
      ),
    tracesSampleRate: 0.05,
    beforeSend(event) {
      const clean = sanitizeMainSentryEvent(event)
      if (clean.contexts) delete clean.contexts.startup_resources
      const active = startupAttempt()
      const captured = (event.timestamp ?? 0) * 1000
      if (
        active &&
        captured >= active.wallStart &&
        captured <= Date.now() &&
        (event.exception?.values?.length ||
          event.tags?.renderer_gone_reason ||
          event.tags?.startup_failure)
      ) {
        const summary = active.snapshot(true)
        if (
          summary.coverage === 'sampled' &&
          ['<1s', '1-5s', '5-15s'].includes(summary.sample_age)
        ) {
          clean.contexts = { ...clean.contexts, startup_resources: allowedFields(summary) }
        }
      }
      return clean
    },
    beforeSendTransaction: sanitizeMainSentryEvent,
  })
  Sentry.setTag('component', 'electron-main')
  sentryStarted = true
}

export const setMainTelemetryEnabled = (enabled: boolean) => {
  if (isDevelopmentEnvironment()) return

  const client = Sentry.getClient()
  if (client && client.getOptions().enabled !== enabled) telemetryGeneration++
  if (!enabled) {
    if (client) client.getOptions().enabled = false
    return
  }

  if (client) {
    client.getOptions().enabled = true
  } else if (!sentryStarted) {
    startSentry()
  }
}

export const configureMainSentry = (enabled: boolean) => {
  setMainTelemetryEnabled(enabled)
}

export const recordMainCount = (name: string, attributes: MetricAttributes, value = 1) => {
  if (!isSentryEnabled()) return

  try {
    Sentry.metrics.count(name, value, { attributes })
  } catch {
    // 遥测失败不能影响主流程。
  }
}

export const recordMainDuration = (
  name: string,
  durationMs: number,
  attributes: MetricAttributes
) => {
  if (!isSentryEnabled()) return

  try {
    Sentry.metrics.distribution(name, durationMs, {
      unit: 'millisecond',
      attributes,
    })
  } catch {
    // 遥测失败不能影响主流程。
  }
}

export const observeMainOperation = <T>(
  name: string,
  op: string,
  attributes: MetricAttributes,
  callback: () => Promise<T>
): Promise<T> => {
  if (!isSentryEnabled()) return callback()
  return Sentry.startSpan({ name, op, attributes }, callback)
}

/** Runtime 无法自行上报的桌面准备失败，只使用初始化策略已验证的阶段和错误码。 */
export function captureStartupHostFailure(stage: string, code: string) {
  if (!isSentryEnabled() || !startupAttempt()) return
  try {
    Sentry.captureMessage('桌面启动准备失败', {
      level: 'error',
      tags: { component: 'electron-main', startup_failure: stage, known_code: code },
      fingerprint: ['desktop-startup', stage, code],
    })
  } catch {
    /* 不影响原有错误展示。 */
  }
}

export const recordMainStartup = () => {
  recordMainDuration('auto_mas.app.startup.duration', performance.now() - processStartedAt, {
    component: 'electron-main',
  })
}

/**
 * 上报渲染进程崩溃。
 *
 * Minidump 集成在上面被整体过滤掉了（Windows minidump 含完整命令行与环境变量块，
 * 且附件拼进 envelope 的时机在 beforeSend 之后，脱敏钩子够不到），所以渲染进程
 * 崩溃不会自动进 Sentry。这里补一条只带 reason/exitCode 的结构化事件。
 */
export const captureMainRendererCrash = (details: RendererCrashDetails) => {
  if (!isSentryEnabled()) return

  try {
    Sentry.captureMessage(`渲染进程退出: ${details.reason}`, {
      level: 'fatal',
      tags: {
        component: 'electron-main',
        renderer_gone_reason: details.reason,
        renderer_recovery_action: details.action,
      },
      extra: {
        exitCode: details.exitCode,
        crashCount: details.crashCount,
      },
    })
  } catch {
    // 遥测失败不能影响恢复流程。
  }
}

/** 与重载开始时的采集代次绑定，关闭再开启也不补报旧尝试。 */
export const beginMainRendererReload = (details: RendererCrashDetails) => {
  const client = isSentryEnabled() ? Sentry.getClient() : undefined
  const generation = telemetryGeneration
  return (result: RendererReloadResult) => {
    if (!client || client !== Sentry.getClient() || generation !== telemetryGeneration) return
    if (!isSentryEnabled()) return
    try {
      Sentry.captureMessage(`渲染进程重载结果: ${result.outcome}`, {
        level:
          result.outcome === 'failure'
            ? 'error'
            : result.outcome === 'unknown'
              ? 'warning'
              : 'info',
        tags: {
          component: 'electron-main',
          renderer_gone_reason: details.reason,
          renderer_recovery_action: details.action,
          renderer_recovery_outcome: result.outcome,
          renderer_recovery_result: result.resultKind,
        },
        extra: {
          exitCode: details.exitCode,
          crashCount: details.crashCount,
          durationMs: Math.round(result.durationMs),
          loadErrorCode: result.loadErrorCode,
        },
      })
    } catch {
      // 遥测失败不能影响恢复流程。
    }
  }
}
