import * as Sentry from '@sentry/electron/renderer'
import * as VueSentry from '@sentry/vue'
import type { App } from 'vue'
import type { Router } from 'vue-router'

import { sanitizeSentryEvent } from './sentryPrivacy'

let sentryContext: { app: App; router: Router } | undefined
type VueSentryOptions = NonNullable<Parameters<typeof VueSentry.init>[0]>

const startSentry = () => {
  if (!sentryContext) return
  // 开发环境不上报
  if (import.meta.env.DEV) return

  Sentry.init<VueSentryOptions>(
    {
      app: sentryContext.app,
      sendDefaultPii: false,
      dataCollection: {
        userInfo: false,
        cookies: false,
        httpHeaders: {
          request: false,
          response: false,
        },
        httpBodies: [],
        urlQueryParams: false,
        graphQL: {
          document: false,
          variables: false,
        },
        genAI: {
          inputs: false,
          outputs: false,
        },
        databaseQueryData: false,
        stackFrameVariables: false,
        frameContextLines: 0,
      },
      attachProps: false,
      integrations: [
        VueSentry.browserTracingIntegration({ router: sentryContext.router }),
        Sentry.breadcrumbsIntegration({
          console: false,
          dom: false,
          history: false,
        }),
      ],
      tracesSampleRate: 0.05,
      tracePropagationTargets: [/^http:\/\/(?:localhost|127\.0\.0\.1):36163\//],
      beforeSend: sanitizeSentryEvent,
      beforeSendTransaction: sanitizeSentryEvent,
    },
    VueSentry.init
  )
  Sentry.setTag('component', 'electron-renderer')
}

export const setTelemetryEnabled = (enabled: boolean) => {
  const client = Sentry.getClient()

  if (!enabled) {
    if (client) client.getOptions().enabled = false
    return
  }

  if (client) {
    client.getOptions().enabled = true
  } else {
    startSentry()
  }
}

export const configureSentry = (app: App, router: Router, enabled: boolean) => {
  sentryContext = { app, router }
  setTelemetryEnabled(enabled)
}

export const recordRendererStartup = (durationMs: number) => {
  if (Sentry.getClient()?.getOptions().enabled !== true) return

  try {
    Sentry.metrics.distribution('auto_mas.app.startup.duration', durationMs, {
      unit: 'millisecond',
      attributes: { component: 'electron-renderer' },
    })
  } catch {
    // 遥测失败不能影响前端启动。
  }
}
