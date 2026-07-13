import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'

export type HSREngine = 'SRA' | 'M7A'

export interface HSRAdapterCapability {
  engine: HSREngine
  display_name: string
  version: string
  supported_modes: string[]
  capabilities: string[]
  ready?: boolean | null
  ready_reason?: string
}

export interface HSRTaskCapability {
  key: string
  name: string
  phase: 'daily' | 'weekly' | 'monthly'
  description: string
  engines: HSREngine[]
}

export interface HSRCapabilitySnapshot {
  revision: number
  available: boolean
  unavailable_reason?: string | null
  candidate_engines: HSREngine[]
  selected_engines: HSREngine[]
  effective_engines: HSREngine[]
  supported_modes: string[]
  adapters: HSRAdapterCapability[]
  tasks: HSRTaskCapability[]
  warnings: string[]
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

  const importM7AAbyssSnapshot = async (scriptId: string, userId: string) => {
    return requestPluginData(
      axios.post<PluginEnvelope<Record<string, unknown>>>(url('/m7a/abyss-snapshot/import'), {
        scriptId,
        userId,
      })
    )
  }

  return { getCapabilities, getStageOptions, importM7AAbyssSnapshot }
}
