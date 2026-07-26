/**
 * 插件管理视图共享类型。
 * 从 Plugin.vue 提取，避免重复定义。
 */

export interface PluginInstance {
  id: string
  plugin: string
  enabled: boolean
  name: string
  config: Record<string, unknown>
  system?: boolean
  locked?: boolean
  visible?: boolean
}

export interface PluginSchemaField {
  type: string
  title?: string
  format?: string
  default?: unknown
  required?: boolean
  description?: string
  placeholder?: string
  help?: string
  rows?: number
  item_type?: string
  enum?: unknown[]
  examples?: unknown[]
  constraints?: Record<string, unknown>
  action?: PluginSchemaAction
  button?: PluginSchemaAction
  configurable?: boolean
}

export interface PluginSchemaAction {
  label?: string
  path?: string
  method?: string
  payload?: unknown
  refresh?: boolean
}

export interface PluginPackageInfo {
  package: string
  version?: string | null
  source?: string
  path?: string | null
}

export interface PluginsGetResponse {
  code: number
  status: string
  message: string
  version: number
  discovered_plugins: string[]
  schemas: Record<string, Record<string, PluginSchemaField>>
  schema_errors: Record<string, string>
  plugin_services?: Record<string, PluginServiceInfo>
  plugin_routes?: Record<string, PluginRouteInfo[]>
  plugin_actions?: Record<string, PluginActionInfo[]>
  plugin_packages?: Record<string, PluginPackageInfo>
  instances: PluginInstance[]
  runtime_states: Record<string, PluginRuntimeState>
}

export interface PluginServiceInfo {
  provides: string[]
  needs: string[]
  wants: string[]
}

export interface PluginRouteInfo {
  kind: 'http' | 'websocket' | string
  path: string
  methods: string[]
  plugin: string
}

export interface PluginActionInfo {
  id: string
  label: string
  path: string
  method: string
  payload?: unknown
  plugin: string
  refresh?: boolean
}

export interface PluginRuntimeState {
  instance_id: string
  plugin: string
  status: string
  generation: number
  lifecycle_phase: string
  lifecycle_updated_at?: string | null
  reload_count: number
  last_reload_reason?: string | null
  last_reload_at?: string | null
  created_at?: string | null
  discovered_at?: string | null
  loaded_at?: string | null
  activated_at?: string | null
  disposed_at?: string | null
  unloaded_at?: string | null
  last_error?: string | null
  last_error_at?: string | null
}

export interface ServiceDeclarationRow {
  key: 'provides' | 'needs' | 'wants'
  label: string
  color: string
  value: string
}

export interface DiscoveredPluginOption {
  name: string
  instanceCount: number
  serviceCount: number
  routeCount: number
  schemaError: string
  description: string
  searchText: string
}

export interface WsCommandResponse<T = unknown> {
  success?: boolean
  message?: string
  code?: number
  data?: T
  request_id?: string
}

export interface PluginListLayoutState {
  version: 1
  groupOrder: string[]
  instanceOrder: string[]
  instanceGroups: Record<string, string>
}

export interface PluginSystemRuntimeMessage {
  kind: 'runtime_state'
  event: string
  record: PluginRuntimeState
}

export interface PluginSystemSnapshotMessage extends PluginsGetResponse {
  kind: 'snapshot'
  reason?: string
}

export interface PluginSystemHmrMessage {
  kind: 'hmr'
  event: string
  plugin?: string | null
  changed_files?: string[]
  action: string
  status: 'running' | 'success' | 'error' | string
  message?: string
}

// ---- 生命周期状态 ----

export type PluginLifecycleStatus =
  | 'discovered'
  | 'installed'
  | 'activating'
  | 'active'
  | 'update'
  | 'deactivating'
  | 'failed'
  | 'disabled'
  | 'restart-required'

export const LIFECYCLE_STATUS_LABELS: Record<PluginLifecycleStatus, string> = {
  discovered: '已发现',
  installed: '已安装',
  activating: '激活中',
  active: '运行中',
  update: '更新可用',
  deactivating: '停用中',
  failed: '异常',
  disabled: '已禁用',
  'restart-required': '需重启',
}

export const LIFECYCLE_STATUS_COLORS: Record<PluginLifecycleStatus, string> = {
  discovered: 'default',
  installed: 'blue',
  activating: 'processing',
  active: 'success',
  update: 'orange',
  deactivating: 'warning',
  failed: 'error',
  disabled: 'default',
  'restart-required': 'purple',
}

export const STATUS_LABELS: Record<string, string> = {
  active: '运行中',
  loaded: '已加载',
  configured: '待配置',
  discovered: '已发现',
  error: '异常',
  disposed: '已销毁',
  unloaded: '已卸载',
}

export const PHASE_LABELS: Record<string, string> = {
  active: '已激活',
  discovered: '已发现',
  loaded: '已加载',
  configured: '已配置',
  on_load: '加载中',
  on_start: '启动中',
  on_stop: '停止中',
  on_unload: '卸载中',
  on_reload_prepare: '重载准备',
  on_reload_commit: '重载提交',
  on_reload_rollback: '重载回滚',
  reload_failed: '重载失败',
  disposed: '已销毁',
  unloaded: '已卸载',
  idle: '空闲',
}

export const SERVICE_DECLARATION_DEFS = [
  { key: 'provides', label: '提供服务', color: 'green' },
  { key: 'needs', label: '必须服务', color: 'red' },
  { key: 'wants', label: '可选服务', color: 'gold' },
] as const
