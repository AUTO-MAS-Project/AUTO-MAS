import type { ComponentHint, PluginConfigUi } from '@/api'

export function pluginActionHint(
  ui: PluginConfigUi | null | undefined,
  group: string,
  field: string
): ComponentHint | undefined {
  // 隐藏项不会出现在 hints 中；按钮可用性读取 editable，不推断插件运行状态。
  return ui?.hints?.[group]?.find(hint => hint.field === field)
}

export function pluginToggleChecked(ui: PluginConfigUi | undefined, enabled: unknown): boolean {
  // 可执行的停用表示已启用，可执行的启用表示已停用；忙碌或只读时保留当前展示值。
  if (pluginActionHint(ui, 'info', 'disable')?.editable === true) return true
  if (pluginActionHint(ui, 'info', 'enable')?.editable === true) return false
  return enabled === true
}
