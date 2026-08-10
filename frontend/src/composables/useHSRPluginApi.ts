import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'

/** Engines exposed by the built-in HSR adapter. */
export type HSREngine = 'SRA' | 'M7A'

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
  version?: string | null
  supported_modes: string[]
  capabilities: string[] | Record<string, unknown>
  ready?: boolean | null
  ready_reason?: string
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
  key?: string
  engine: HSREngine
  fields: HSRManagedField[]
  source?: string | null
  warnings?: string[]
}

export interface HSRManagedTask extends HSRTaskCapability {
  forms: Partial<Record<HSREngine, HSRManagedEngineForm>>
}

export interface HSRManagedConfigSnapshot {
  revision: number | string
  tasks: HSRManagedTask[]
  task_mapping: Record<string, HSREngine>
  warnings: string[]
}

export interface HSRDirectConfigImportResult {
  engine: HSREngine
  source?: string | null
  imported_at?: string | null
  size?: number
}

export interface HSRCapabilitySnapshot {
  revision: number | string
  available: boolean
  unavailable_reason?: string | null
  candidate_engines: HSREngine[]
  configured_engines: HSREngine[]
  effective_engines: HSREngine[]
  supported_modes: string[]
  adapters: HSRAdapterCapability[] | Record<string, HSRAdapterCapability>
  tasks: HSRTaskCapability[] | Record<string, HSRTaskCapability>
  warnings: string[]
  browser?: HSRBrowserCapability
}

/**
 * Capability responses may contain diagnostics intended for developers rather
 * than script users.  Keep those diagnostics available to callers, but avoid
 * surfacing the built-in old-dev implementation notes in the editor banners.
 */
export const filterHSRCapabilityWarnings = (warnings?: readonly string[] | null): string[] =>
  (warnings ?? []).filter(
    warning =>
      !warning.startsWith('old dev 使用内置 HSRConfig/HSRUserConfig；未加载插件注册表') &&
      !warning.startsWith('能力来源为原生配置域 inspect，未读取配置正文')
  )

interface PluginEnvelope<T> {
  code?: number
  status?: string
  message?: string
  data?: T
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

/**
 * Old dev keeps the HSR API under /api/scripts/hsr.  Keep the adapter client
 * independent from generated OpenAPI services so the plugin-shaped UI can be
 * used with either the old envelope or a direct JSON response.
 */
const url = (path: string) => `${OpenAPI.BASE}/api/scripts/hsr${path}`

const unwrap = <T>(response: { data: PluginEnvelope<T> | T }): T => {
  const payload = response.data as PluginEnvelope<T>
  if (payload && typeof payload === 'object' && 'code' in payload && payload.code !== undefined) {
    if (payload.code !== 200) {
      throw new Error(payload.message || 'HSR 请求失败')
    }
    return (payload.data === undefined ? payload : payload.data) as T
  }
  return response.data as T
}

const requestPluginData = async <T>(
  request: Promise<{ data: PluginEnvelope<T> | T }>
): Promise<T> => {
  try {
    return unwrap(await request)
  } catch (error) {
    if (axios.isAxiosError<PluginEnvelope<unknown>>(error)) {
      const payload = error.response?.data
      if (payload && typeof payload === 'object' && 'message' in payload && payload.message) {
        throw new Error(String(payload.message))
      }
    }
    throw error
  }
}

const normalizeStageOptions = (
  data: { engine: HSREngine; categories?: Array<Record<string, any>> } | undefined,
  engine: HSREngine
): { engine: HSREngine; categories: HSRStageCategory[] } => ({
  engine: data?.engine || engine,
  categories: (data?.categories || []).map(category => ({
    key: String(category.key ?? category.categoryKey ?? ''),
    label: String(
      category.label ?? category.categoryLabel ?? category.key ?? category.categoryKey ?? ''
    ),
    options: (Array.isArray(category.options) ? category.options : []).map(option => ({
      id: String(option.id ?? option.value ?? ''),
      label: String(option.label ?? option.name ?? option.value ?? ''),
      detail: String(option.detail ?? ''),
      cost: option.cost ?? category.cost ?? null,
      max_count:
        option.max_count ?? option.maxCount ?? category.max_count ?? category.maxCount ?? null,
      native_payload:
        option.native_payload && typeof option.native_payload === 'object'
          ? option.native_payload
          : {
              ...(option.m7a ? { m7a: option.m7a } : {}),
              ...(option.sra ? { sra: option.sra } : {}),
            },
    })),
  })),
})

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
    const data = await requestPluginData<{
      engine: HSREngine
      categories?: Array<Record<string, any>>
    }>(
      axios.get<PluginEnvelope<{ engine: HSREngine; categories?: Array<Record<string, any>> }>>(
        url('/stage-options'),
        { params: { scriptId, userId, engine, slot } }
      )
    )
    return normalizeStageOptions(data, engine)
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

  return {
    getCapabilities,
    getStageOptions,
    getManagedConfig,
    importDirectConfig,
  }
}
