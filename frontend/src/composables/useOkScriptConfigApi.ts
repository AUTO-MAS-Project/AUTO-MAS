import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'

export interface OkScriptConfigField {
  name: string
  type: string
  label: string
  description: string
  value: unknown
  options: string[] | null
  min: number | null
  max: number | null
  step: number | null
  section?: string
  sectionPriority?: number
  priority?: number
  advanced?: boolean
}

export interface OkScriptConfigFile {
  filename: string
  displayName: string
  group: string
  taskIndex: number | null
  fieldCount: number
  fields: OkScriptConfigField[]
  currentData: Record<string, unknown>
}

export interface OkScriptProviderMetadata {
  resourceName: string
  displayName: string
  taskOptions: Array<{ value: number; label: string }>
  accountFields: {
    enabledKey: string
    independentKey: string
    accountListKey: string
  } | null
  runtimeVerified?: boolean
  runtimeBlockReason?: string
}

export interface OkScriptConfigListResponse {
  code?: number
  status?: string
  message?: string
  data?: OkScriptConfigFile[]
  optionLabels?: Record<string, string>
  configPath?: string
  provider?: OkScriptProviderMetadata
}

export interface OkScriptConfigUpdateResponse {
  code?: number
  status?: string
  message?: string
  data?: string[]
}

export type OkScriptConfigPatchMap = Record<string, Record<string, unknown>>

export const useOkScriptConfigApi = (endpointPrefix: string) => {
  const requestUrl = (path: string) => `${OpenAPI.BASE}${endpointPrefix}${path}`
  const isPluginEndpoint = () => endpointPrefix.startsWith('/plugin/')

  const listConfigFiles = async (
    scriptId: string,
    userId: string
  ): Promise<OkScriptConfigListResponse> => {
    if (isPluginEndpoint()) {
      const response = await axios.post(requestUrl('/list'), {
        script_id: scriptId,
        user_id: userId,
      })
      return response.data
    }

    const response = await axios.post(requestUrl('/list'), null, {
      params: {
        script_id: scriptId,
        user_id: userId,
      },
    })
    return response.data
  }

  const batchUpdateConfigFiles = async (
    scriptId: string,
    userId: string,
    configsToUpdate: OkScriptConfigPatchMap
  ): Promise<OkScriptConfigUpdateResponse> => {
    const response = await axios.post(requestUrl('/batch-update'), {
      script_id: scriptId,
      user_id: userId,
      configs: configsToUpdate,
    })
    return response.data
  }

  return {
    listConfigFiles,
    batchUpdateConfigFiles,
  }
}
