/**
 * 插件 Schema 校验与字段类型 composable。
 * 从 Plugin.vue 提取 schema 相关的纯函数逻辑。
 */

import type { PluginSchemaField, PluginSchemaAction } from '../types'

// ---- 类型判断 ----

export function isBooleanSchema(fieldSchema: PluginSchemaField): boolean {
  return fieldSchema.type === 'boolean' || fieldSchema.type === 'bool'
}

export function isStringSchema(fieldSchema: PluginSchemaField): boolean {
  return fieldSchema.type === 'string' || fieldSchema.type === 'str'
}

export function isNumberSchema(fieldSchema: PluginSchemaField): boolean {
  return (
    fieldSchema.type === 'number' ||
    fieldSchema.type === 'integer' ||
    fieldSchema.type === 'int' ||
    fieldSchema.type === 'float'
  )
}

export function isListSchema(fieldSchema: PluginSchemaField): boolean {
  return fieldSchema.type === 'list' || fieldSchema.type.startsWith('list[')
}

export function isPasswordSchema(fieldSchema: PluginSchemaField): boolean {
  return isStringSchema(fieldSchema) && fieldSchema.format === 'password'
}

export function isUrlSchema(fieldSchema: PluginSchemaField): boolean {
  return isStringSchema(fieldSchema) && fieldSchema.format === 'url'
}

export function isEmailSchema(fieldSchema: PluginSchemaField): boolean {
  return isStringSchema(fieldSchema) && fieldSchema.format === 'email'
}

export function isEnumSchema(fieldSchema: PluginSchemaField): boolean {
  return (
    Array.isArray(fieldSchema.enum) && fieldSchema.enum.length > 0 && !isEnumListSchema(fieldSchema)
  )
}

export function isEnumListSchema(fieldSchema: PluginSchemaField): boolean {
  return Array.isArray(fieldSchema.enum) && fieldSchema.enum.length > 0 && isListSchema(fieldSchema)
}

export function isButtonSchema(fieldSchema: PluginSchemaField): boolean {
  return fieldSchema.type === 'button' || fieldSchema.type === 'action'
}

export function hasEnableSchema(
  pluginName: string | undefined,
  schemaMap: Record<string, Record<string, PluginSchemaField>>
): boolean {
  if (!pluginName) return false
  const schema = schemaMap[pluginName]
  return Boolean(schema && schema.enable && isBooleanSchema(schema.enable))
}

// ---- 约束提取 ----

export function toFiniteNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

export function getSchemaConstraint(fieldSchema: PluginSchemaField, key: string): unknown {
  return fieldSchema.constraints?.[key]
}

// ---- 字段标签 ----

export function getFieldLabel(field: string, fieldSchema: PluginSchemaField): string {
  return fieldSchema.title || fieldSchema.description || field
}

export function getTypeLabel(fieldSchema: PluginSchemaField): string {
  if (isButtonSchema(fieldSchema)) return '按钮'
  if (isEnumSchema(fieldSchema)) return '选项'
  if (isEnumListSchema(fieldSchema)) return '多选'
  if (isPasswordSchema(fieldSchema)) return '密码'
  if (isStringSchema(fieldSchema)) return '字符串'
  if (isNumberSchema(fieldSchema)) return '数字'
  if (isBooleanSchema(fieldSchema)) return '布尔'
  if (isListSchema(fieldSchema)) return '列表'
  if (fieldSchema.type === 'key_value') return '键值对'
  if (fieldSchema.type === 'table') return '表格'
  return fieldSchema.type
}

// ---- Schema 按钮 Action ----

export function getSchemaButtonActionId(field: string): string {
  return field
}

export function getSchemaButtonAction(
  field: string,
  fieldSchema: PluginSchemaField,
  pluginName: string
): {
  id: string
  label: string
  path: string
  method: string
  payload: unknown
  plugin: string
  refresh: boolean
} | null {
  const action = fieldSchema.action || fieldSchema.button
  if (!action || typeof action !== 'object') return null
  if (
    typeof (action as PluginSchemaAction).path !== 'string' ||
    !(action as PluginSchemaAction).path?.trim()
  )
    return null
  return {
    id: getSchemaButtonActionId(field),
    label: (action as PluginSchemaAction).label || getFieldLabel(field, fieldSchema),
    path: (action as PluginSchemaAction).path!,
    method: (action as PluginSchemaAction).method || 'POST',
    payload: (action as PluginSchemaAction).payload ?? {},
    plugin: pluginName,
    refresh: Boolean((action as PluginSchemaAction).refresh),
  }
}

// ---- 配置文本工具 ----

export function parseConfigText(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('配置必须是 JSON 对象')
  }
  return parsed as Record<string, unknown>
}

export function setConfigObjectToText(config: Record<string, unknown>): string {
  return JSON.stringify(config, null, 2)
}

// ---- 校验 ----

export function isValidHttpUrl(value: string): string {
  try {
    const parsed = new URL(value)
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return '请输入 http 或 https URL'
    }
    const hostname = parsed.hostname
    if (!hostname) return '请输入有效的 URL'
    if (hostname === 'localhost' || isIpv4Host(hostname) || isIpv6Host(hostname)) return ''
    if (!isValidDomainHost(hostname)) return '请输入有效的域名、localhost 或 IP 地址'
    return ''
  } catch {
    return '请输入有效的 URL'
  }
}

function isIpv4Host(host: string): boolean {
  const parts = host.split('.')
  return (
    parts.length === 4 &&
    parts.every(part => {
      if (!/^\d{1,3}$/.test(part)) return false
      const value = Number(part)
      return value >= 0 && value <= 255
    })
  )
}

function isIpv6Host(host: string): boolean {
  return host.includes(':')
}

function isValidDomainHost(host: string): boolean {
  const labels = host.split('.')
  if (labels.length < 2) return false
  const tld = labels[labels.length - 1]
  if (!/^[a-zA-Z]{2,}$/.test(tld)) return false
  return labels.every(label => /^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(label))
}

export function validateSchemaFieldValue(
  field: string,
  fieldSchema: PluginSchemaField,
  value: unknown
): string {
  if (isButtonSchema(fieldSchema)) return ''

  if (value === undefined || value === null || value === '') {
    return fieldSchema.required ? '该字段为必填项' : ''
  }

  if (isStringSchema(fieldSchema)) {
    const text = String(value)
    const minLength = toFiniteNumber(getSchemaConstraint(fieldSchema, 'min_length'))
    const maxLength = toFiniteNumber(getSchemaConstraint(fieldSchema, 'max_length'))
    const pattern = getSchemaConstraint(fieldSchema, 'pattern')
    if (minLength !== undefined && text.length < minLength) return `至少需要 ${minLength} 个字符`
    if (maxLength !== undefined && text.length > maxLength) return `最多允许 ${maxLength} 个字符`
    if (typeof pattern === 'string' && pattern) {
      try {
        if (!new RegExp(pattern).test(text)) return '内容不符合格式要求'
      } catch {
        return ''
      }
    }
    if (isUrlSchema(fieldSchema)) {
      const urlError = isValidHttpUrl(text)
      if (urlError) return urlError
    }
    if (isEmailSchema(fieldSchema)) {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) return '请输入有效的邮箱地址'
    }
  }

  if (isNumberSchema(fieldSchema)) {
    const numberValue = toFiniteNumber(value)
    if (numberValue === undefined) return '请输入有效数字'
    const ge = toFiniteNumber(getSchemaConstraint(fieldSchema, 'ge'))
    const le = toFiniteNumber(getSchemaConstraint(fieldSchema, 'le'))
    const gt = toFiniteNumber(getSchemaConstraint(fieldSchema, 'gt'))
    const lt = toFiniteNumber(getSchemaConstraint(fieldSchema, 'lt'))
    if (ge !== undefined && numberValue < ge) return `不能小于 ${ge}`
    if (le !== undefined && numberValue > le) return `不能大于 ${le}`
    if (gt !== undefined && numberValue <= gt) return `必须大于 ${gt}`
    if (lt !== undefined && numberValue >= lt) return `必须小于 ${lt}`
  }

  return ''
}

export function collectSchemaFieldErrors(
  schemaEntries: [string, PluginSchemaField][],
  configText: string
): Record<string, string> {
  const errors: Record<string, string> = {}
  let config: Record<string, unknown>
  try {
    config = parseConfigText(configText)
  } catch {
    return errors
  }
  for (const [field, fieldSchema] of schemaEntries) {
    const error = validateSchemaFieldValue(field, fieldSchema, config[field])
    if (error) errors[field] = error
  }
  return errors
}
