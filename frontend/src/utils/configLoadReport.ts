// 配置加载报告（GET /api/setting/config-load）的展示映射。
//
// 状态与规范化事件都来自后端：页面只认这里的映射，避免把英文枚举原样显示给用户，
// 也避免 unknown 状态在界面上消失。技术原文（路径、原值/新值）由调用方原样展示。
import dayjs from 'dayjs'

/**
 * 后端 ConfigLoadReportOut.status 的展示用联合类型。
 * 与生成模型保持一致；后端将来新增取值时走 unknown 回退，不会显示原始枚举。
 */
export type ConfigLoadStatus = 'ok' | 'empty' | 'corrupt_recovered' | 'unreadable' | 'defaulted'

/** 状态 → i18n 键（key 的取值由 configLoadReport.test.ts 保证三语齐全）。 */
export const CONFIG_LOAD_STATUS_KEYS: Record<ConfigLoadStatus, string> = {
  ok: 'setting.configLoad.status.ok',
  empty: 'setting.configLoad.status.empty',
  corrupt_recovered: 'setting.configLoad.status.corruptRecovered',
  unreadable: 'setting.configLoad.status.unreadable',
  defaulted: 'setting.configLoad.status.defaulted',
}

export const CONFIG_LOAD_STATUS_COLORS: Record<ConfigLoadStatus, string> = {
  ok: 'green',
  empty: 'default',
  corrupt_recovered: 'red',
  unreadable: 'red',
  defaulted: 'orange',
}

export const CONFIG_LOAD_UNKNOWN_STATUS_KEY = 'setting.configLoad.status.unknown'

export function configLoadStatusKey(status: string): string {
  return CONFIG_LOAD_STATUS_KEYS[status as ConfigLoadStatus] ?? CONFIG_LOAD_UNKNOWN_STATUS_KEY
}

export function configLoadStatusColor(status: string): string {
  return CONFIG_LOAD_STATUS_COLORS[status as ConfigLoadStatus] ?? 'default'
}

export type ConfigLoadTranslate = (key: string, named?: Record<string, unknown>) => string

/** 原值为空时占位，避免「→」两侧看不见东西。 */
const VALUE_PLACEHOLDER = '—'

/** 「字段：原值 → 新值」，原因与时间由调用方单独渲染。 */
export function configLoadEventSummary(
  t: ConfigLoadTranslate,
  event: { field: string; oldValue: string; newValue: string }
): string {
  return t('setting.configLoad.event.summary', {
    field: event.field,
    old: event.oldValue || VALUE_PLACEHOLDER,
    new: event.newValue || VALUE_PLACEHOLDER,
  })
}

export function hasNormalizationEvents(events?: unknown[] | null): boolean {
  return (events?.length ?? 0) > 0
}

/** 后端给的是 ISO 时间串；解析不了就原样返回，绝不显示 Invalid Date。 */
export function formatConfigLoadTime(value?: string | null): string {
  if (!value) return ''
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : value
}
