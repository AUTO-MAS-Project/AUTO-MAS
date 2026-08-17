import type { Event, Stacktrace } from '@sentry/vue'

import * as Sentry from '@sentry/vue'
import type { App } from 'vue'
import type { Router } from 'vue-router'

const PRIVATE_REQUEST_FIELDS = ['cookies', 'data', 'env', 'headers', 'query_string'] as const
const LOCAL_PATH_PATTERN = /^(?:file:\/\/|[a-zA-Z]:[\\/])/
const PRIVATE_SPAN_DATA_PATTERN = /(?:^|[._-])(body|cookie|header|query)(?:$|[._-])/i
const URL_SPAN_DATA_PATTERN = /(?:^|[._-])(file|filename|path|uri|url)(?:$|[._-])/i

let sentryContext: { app: App; router: Router } | undefined

const stripUrlDetails = (value: string) => value.split(/[?#]/, 1)[0]

const sanitizePath = (value: string) => {
  const sanitized = stripUrlDetails(value)
  if (!LOCAL_PATH_PATTERN.test(sanitized)) return sanitized

  const normalized = sanitized.replace(/\\/g, '/')
  return normalized.slice(normalized.lastIndexOf('/') + 1) || '<local-file>'
}

const sanitizeStacktrace = (stacktrace?: Stacktrace) => {
  for (const frame of stacktrace?.frames ?? []) {
    if (frame.filename) frame.filename = sanitizePath(frame.filename)
    if (frame.module) frame.module = sanitizePath(frame.module)
    delete frame.abs_path
    delete frame.vars
    delete frame.context_line
    delete frame.pre_context
    delete frame.post_context
    delete frame.module_metadata
  }
}

export const sanitizeSentryEvent = <T extends Event>(event: T): T => {
  delete event.user
  delete event.extra
  delete event.server_name

  if (event.request) {
    for (const field of PRIVATE_REQUEST_FIELDS) delete event.request[field]
    if (event.request.url) event.request.url = sanitizePath(event.request.url)
  }

  if (event.transaction) event.transaction = sanitizePath(event.transaction)
  for (const exception of event.exception?.values ?? []) {
    sanitizeStacktrace(exception.stacktrace)
  }
  for (const thread of event.threads?.values ?? []) {
    sanitizeStacktrace(thread.stacktrace)
  }

  for (const breadcrumb of event.breadcrumbs ?? []) {
    if (!breadcrumb.data) continue
    for (const field of PRIVATE_REQUEST_FIELDS) delete breadcrumb.data[field]
    for (const field of ['url', 'from', 'to']) {
      if (typeof breadcrumb.data[field] === 'string') {
        breadcrumb.data[field] = sanitizePath(breadcrumb.data[field])
      }
    }
  }

  for (const span of event.spans ?? []) {
    for (const [key, value] of Object.entries(span.data)) {
      if (PRIVATE_SPAN_DATA_PATTERN.test(key)) {
        delete span.data[key]
      } else if (URL_SPAN_DATA_PATTERN.test(key) && typeof value === 'string') {
        span.data[key] = sanitizePath(value)
      }
    }
  }

  for (const image of event.debug_meta?.images ?? []) {
    if (image.code_file) image.code_file = sanitizePath(image.code_file)
  }

  return event
}

const startSentry = () => {
  if (!sentryContext) return
  // 开发环境不上报
  if (import.meta.env.DEV) return

  Sentry.init({
    app: sentryContext.app,
    dsn: 'https://6ad15803ac77e44f24f46f2dfa599def@o4511881138733056.ingest.us.sentry.io/4511902510678016',
    release: `auto-mas@${import.meta.env.VITE_APP_VERSION}`,
    environment: 'production',
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
      Sentry.browserTracingIntegration({ router: sentryContext.router }),
      Sentry.breadcrumbsIntegration({
        console: false,
        dom: false,
        history: false,
      }),
    ],
    tracesSampleRate: 0.1,
    tracePropagationTargets: [/^http:\/\/(?:localhost|127\.0\.0\.1):36163\//],
    beforeSend: sanitizeSentryEvent,
    beforeSendTransaction: sanitizeSentryEvent,
  })
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
