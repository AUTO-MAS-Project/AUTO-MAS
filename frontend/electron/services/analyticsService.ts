import { app, net } from 'electron'
import { release } from 'os'
import { readBackendDocument } from './backendConfig'
import { getAppRoot } from './environmentService'
import { isDevelopmentEnvironment } from './instanceConfig'
import { AnalyticsService } from './analytics'

const APP_KEY = 'A-SH-2309665908'
const EVENT_URL = 'https://telemetry.auto-mas.top/api/v0/event'
let reportedPreference: boolean | undefined
let preferenceTimer: ReturnType<typeof setTimeout> | undefined

function isAnalyticsAllowed(): boolean {
  return (
    !process.env.VITEST &&
    !process.env.CI &&
    process.env.NODE_ENV !== 'test' &&
    app.isReady() &&
    !isDevelopmentEnvironment() &&
    process.env.AUTO_MAS_TELEMETRY !== 'disabled' &&
    process.env.AUTO_MAS_ENV !== 'development' &&
    !process.env.AUTO_MAS_E2E_DATA_ROOT &&
    !process.env.AUTO_MAS_E2E_REAL
  )
}

export const analyticsService = new AnalyticsService({
  isAllowed: isAnalyticsAllowed,
  systemProps: () => ({
    isDebug: false,
    locale: app.getLocale(),
    osName: process.platform === 'win32' ? 'Windows' : process.platform,
    osVersion: release(),
    engineName: 'Chromium',
    engineVersion: process.versions.chrome ?? '',
    appVersion: app.getVersion(),
    sdkVersion: 'auto-mas-aptabase@1',
  }),
  send: async (payload, signal) => {
    const response = await net.fetch(EVENT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'App-Key': APP_KEY },
      credentials: 'omit',
      redirect: 'error',
      signal,
      body: JSON.stringify(payload),
    })
    await response.body?.cancel()
    if (!response.ok) throw new Error('匿名统计服务未接收事件')
  },
})

/** 不使用 frontend_config 中的旧缓存；缺失、损坏或尚未持久化时先停采。 */
export function refreshAnalyticsPreference(): void {
  if (!isAnalyticsAllowed()) {
    analyticsService.setEnabled(false)
    return
  }
  try {
    const config = readBackendDocument(getAppRoot(), 'setting.yaml', 'Config.json') as
      | { Function?: { IfEnableTelemetry?: unknown } }
      | undefined
    analyticsService.setEnabled(
      reportedPreference !== false && config?.Function?.IfEnableTelemetry === true
    )
  } catch {
    analyticsService.setEnabled(false)
  }
}

/** 关闭立即生效；开启还须确认磁盘配置，等候后端现有的保存防抖。 */
export function syncAnalyticsPreference(enabled: unknown): void {
  clearTimeout(preferenceTimer)
  reportedPreference = enabled === true
  refreshAnalyticsPreference()
  if (reportedPreference) {
    preferenceTimer = setTimeout(refreshAnalyticsPreference, 250)
    preferenceTimer.unref()
  }
}

export function disposeAnalytics(): void {
  clearTimeout(preferenceTimer)
  analyticsService.dispose()
}
