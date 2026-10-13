/** 配置项宽度预设；只用于配置组，不参与页面框架布局。 */
const FIELD_SPANS: Record<string, number> = {
  button: 6,
  'dropdown-button': 6,
  switch: 6,
  checkbox: 6,
  bool: 6,
  boolean: 6,
  'toggle-button': 6,
  select: 8,
  'ref-select': 8,
  number: 8,
  input: 12,
  path: 12,
  date: 12,
  datetime: 12,
}

export function configurationFieldSpan(component = 'input', width?: number | null): number {
  const preset = FIELD_SPANS[component.toLowerCase()] ?? 12
  return Math.min(
    24,
    Math.max(1, width != null && Number.isFinite(width) && width > 0 ? Math.round(width) : preset)
  )
}
