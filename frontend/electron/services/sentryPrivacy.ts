import type { Event, Stacktrace } from '@sentry/electron/main'

const PRIVATE_REQUEST_FIELDS = ['cookies', 'data', 'env', 'headers', 'query_string'] as const
const LOCAL_PATH_PATTERN = /^(?:file:\/\/|[a-zA-Z]:[\\/])/
const PRIVATE_SPAN_DATA_PATTERN = /(?:^|[._-])(body|cookie|header|query)(?:$|[._-])/i
const URL_SPAN_DATA_PATTERN = /(?:^|[._-])(file|filename|from|path|to|uri|url)(?:$|[._-])/i

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

const sanitizeData = (data: Record<string, unknown>) => {
  for (const [key, value] of Object.entries(data)) {
    if (PRIVATE_SPAN_DATA_PATTERN.test(key)) {
      delete data[key]
    } else if (URL_SPAN_DATA_PATTERN.test(key) && typeof value === 'string') {
      data[key] = sanitizePath(value)
    }
  }
}

export const sanitizeMainSentryEvent = <T extends Event>(event: T): T => {
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
    sanitizeData(breadcrumb.data)
  }

  for (const span of event.spans ?? []) {
    sanitizeData(span.data)
  }

  for (const image of event.debug_meta?.images ?? []) {
    if (image.code_file) image.code_file = sanitizePath(image.code_file)
  }

  return event
}
