import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'

export type HSREngine = 'SRA' | 'M7A'

export interface HSRNativeConfigOption {
  id: string
  label: string
  path: string
}

export interface HSRNativeControlSnapshot {
  engine: HSREngine
  configurator_ready: boolean
  direct_run_ready: boolean
  configurator_reason: string
  direct_run_reason: string
  launcher_path: string
  selected_config: string
  configs: HSRNativeConfigOption[]
  running?: boolean
  pid?: number | null
}

export interface HSRBrowserCapability {
  service: string
  handoff_protocol?: string
  service_available: boolean
  backend?: 'local' | 'mas_cloud' | 'native_owned'
  ready: boolean
  blockers: string[]
  adapter_bridges?: Array<{
    engine: HSREngine
    upstream_version: string
    compatibility: string
    upstream_supported: boolean
  }>
}

export interface HSRAdapterCapability {
  engine: HSREngine
  display_name: string
  version: string
  supported_modes: string[]
  capabilities: string[]
  ready?: boolean | null
  ready_reason?: string
  native_control?: HSRNativeControlSnapshot
}

export interface HSRTaskCapability {
  key: string
  name: string
  phase: 'daily' | 'weekly'
  description: string
  engines: HSREngine[]
  strategies?: Partial<Record<HSREngine, string[]>>
}

export type HSRManagedFieldType =
  | 'boolean'
  | 'integer'
  | 'number'
  | 'string'
  | 'select'
  | 'json'
  | 'stage'

export interface HSRManagedFieldOption {
  value: unknown
  label: string
}

export interface HSRManagedField {
  key: string
  label: string
  type: HSRManagedFieldType
  value: unknown
  description?: string
  options?: HSRManagedFieldOption[]
  minimum?: number | null
  maximum?: number | null
  readonly?: boolean
}

export interface HSRManagedEngineForm {
  key: string
  engine: HSREngine
  fields: HSRManagedField[]
  source: string
  warnings?: string[]
}

export interface HSRManagedTask extends HSRTaskCapability {
  forms: Partial<Record<HSREngine, HSRManagedEngineForm>>
}

export interface HSRManagedConfigSnapshot {
  revision: number
  tasks: HSRManagedTask[]
  task_mapping: Record<string, HSREngine>
  warnings: string[]
}

export interface HSRDirectConfigImportResult {
  engine: HSREngine
  source: string
  imported_at: string
  size: number
}

export interface HSRCapabilitySnapshot {
  revision: number
  available: boolean
  unavailable_reason?: string | null
  candidate_engines: HSREngine[]
  configured_engines: HSREngine[]
  effective_engines: HSREngine[]
  supported_modes: string[]
  adapters: HSRAdapterCapability[]
  tasks: HSRTaskCapability[]
  warnings: string[]
  browser?: HSRBrowserCapability
}

interface PluginEnvelope<T> {
  code: number
  status: string
  message: string
  data: T
}

export interface HSRStageOption {
  id: string
  label: string
  detail: string
  cost?: number | null
  max_count?: number | null
  native_payload: Record<string, unknown>
}

export interface HSRStageCategory {
  key: string
  label: string
  options: HSRStageOption[]
}

const url = (path: string) => `${OpenAPI.BASE}/plugin/hsr/v1${path}`

const unwrap = <T>(response: { data: PluginEnvelope<T> }): T => {
  if (response.data.code !== 200) {
    throw new Error(response.data.message || 'HSR 插件请求失败')
  }
  return response.data.data
}

const requestPluginData = async <T>(request: Promise<{ data: PluginEnvelope<T> }>): Promise<T> => {
  try {
    return unwrap(await request)
  } catch (error) {
    if (axios.isAxiosError<PluginEnvelope<unknown>>(error)) {
      const message = error.response?.data?.message
      if (message) throw new Error(message)
    }
    throw error
  }
}

export function useHSRPluginApi() {
  const getCapabilities = async (scriptId?: string): Promise<HSRCapabilitySnapshot> => {
    return requestPluginData(
      axios.get<PluginEnvelope<HSRCapabilitySnapshot>>(url('/capabilities'), {
        params: scriptId ? { scriptId } : undefined,
      })
    )
  }

  const getStageOptions = async (
    scriptId: string,
    engine: HSREngine,
    userId?: string,
    slot = 'main'
  ): Promise<{ engine: HSREngine; categories: HSRStageCategory[] }> => {
    return requestPluginData(
      axios.get<PluginEnvelope<{ engine: HSREngine; categories: HSRStageCategory[] }>>(
        url('/stage-options'),
        { params: { scriptId, userId, engine, slot } }
      )
    )
  }

  const getManagedConfig = async (
    scriptId: string,
    userId: string
  ): Promise<HSRManagedConfigSnapshot> => {
    return requestPluginData(
      axios.get<PluginEnvelope<HSRManagedConfigSnapshot>>(url('/managed-config'), {
        params: { scriptId, userId },
      })
    )
  }

  const importDirectConfig = async (
    scriptId: string,
    userId: string,
    engine: HSREngine
  ): Promise<HSRDirectConfigImportResult> => {
    return requestPluginData(
      axios.post<PluginEnvelope<HSRDirectConfigImportResult>>(url('/direct-config/import'), {
        scriptId,
        userId,
        engine,
      })
    )
  }

  const getNativeConfigs = async (
    scriptId: string,
    engine: HSREngine
  ): Promise<HSRNativeControlSnapshot> => {
    return requestPluginData(
      axios.get<PluginEnvelope<HSRNativeControlSnapshot>>(url('/native-configs'), {
        params: { scriptId, engine },
      })
    )
  }

  const openNativeConfigurator = async (
    scriptId: string,
    engine: HSREngine
  ): Promise<HSRNativeControlSnapshot> => {
    return requestPluginData(
      axios.post<PluginEnvelope<HSRNativeControlSnapshot>>(url('/native-config/open'), {
        scriptId,
        engine,
      })
    )
  }

  const getNativeConfiguratorStatus = async (
    scriptId: string,
    engine: HSREngine
  ): Promise<HSRNativeControlSnapshot> => {
    return requestPluginData(
      axios.get<PluginEnvelope<HSRNativeControlSnapshot>>(url('/native-config/status'), {
        params: { scriptId, engine },
      })
    )
  }

  const stopNativeConfigurator = async (
    scriptId: string,
    engine: HSREngine
  ): Promise<{ engine: HSREngine; running: boolean; pid?: number | null }> => {
    return requestPluginData(
      axios.post<PluginEnvelope<{ engine: HSREngine; running: boolean; pid?: number | null }>>(
        url('/native-config/stop'),
        { scriptId, engine }
      )
    )
  }

  return {
    getCapabilities,
    getStageOptions,
    getManagedConfig,
    importDirectConfig,
    getNativeConfigs,
    openNativeConfigurator,
    getNativeConfiguratorStatus,
    stopNativeConfigurator,
  }
}
