import type { Event, Stacktrace } from '@sentry/electron/renderer'

const PRIVATE_REQUEST_FIELDS = ['cookies', 'data', 'env', 'headers', 'query_string'] as const
const LOCAL_PATH_PATTERN = /^(?:file:\/\/|[a-zA-Z]:[\\/])/
const PRIVATE_SPAN_DATA_PATTERN = /(?:^|[._-])(body|cookie|header|query)(?:$|[._-])/i
const URL_SPAN_DATA_PATTERN = /(?:^|[._-])(file|filename|from|path|to|uri|url)(?:$|[._-])/i
// 异常描述与消息正文里嵌着本机绝对路径（Node 的 Error.message 天然带路径），
// 按字段整体裁剪会丢掉排查信息，故只遮蔽其中的用户名段。
const USER_DIR_PATTERN = /((?:[a-zA-Z]:)?[\\/]+(?:Users|home)[\\/]+)([^\\/\r\n"'<>|]+)/gi

const stripUrlDetails = (value: string) => value.split(/[?#]/, 1)[0]

const maskUserDirs = (value: string) => value.replace(USER_DIR_PATTERN, '$1<user>')

const sanitizePath = (value: string) => {
  const sanitized = stripUrlDetails(value)
  if (!LOCAL_PATH_PATTERN.test(sanitized)) return maskUserDirs(sanitized)

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

export const sanitizeSentryEvent = <T extends Event>(event: T): T => {
  delete event.user
  delete event.extra
  delete event.server_name

  if (typeof event.message === 'string') event.message = maskUserDirs(event.message)

  if (event.request) {
    for (const field of PRIVATE_REQUEST_FIELDS) delete event.request[field]
    if (event.request.url) event.request.url = sanitizePath(event.request.url)
  }

  if (event.transaction) event.transaction = sanitizePath(event.transaction)
  for (const exception of event.exception?.values ?? []) {
    sanitizeStacktrace(exception.stacktrace)
    if (exception.value) exception.value = maskUserDirs(exception.value)
  }
  for (const thread of event.threads?.values ?? []) {
    sanitizeStacktrace(thread.stacktrace)
  }

  for (const breadcrumb of event.breadcrumbs ?? []) {
    if (breadcrumb.message) breadcrumb.message = maskUserDirs(breadcrumb.message)
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
