import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'

export interface OkwwConfigField {
  name: string
  type: string
  label: string
  description: string
  value: unknown
  options: string[] | null
  min: number | null
  max: number | null
  step: number | null
}

export interface OkwwConfigFile {
  filename: string
  displayName: string
  group: string
  taskIndex: number | null
  fieldCount: number
  fields: OkwwConfigField[]
  currentData: Record<string, unknown>
}

export interface OkwwConfigListResponse {
  code?: number
  status?: string
  message?: string
  data?: OkwwConfigFile[]
  optionLabels?: Record<string, string>
  configPath?: string
}

export interface OkwwConfigUpdateResponse {
  code?: number
  status?: string
  message?: string
  data?: string[]
}

export type OkwwConfigPatchMap = Record<string, Record<string, unknown>>

export const useOkwwConfigApi = (endpointPrefix: string) => {
  const requestUrl = (path: string) => `${OpenAPI.BASE}${endpointPrefix}${path}`
  const isPluginEndpoint = () => endpointPrefix.startsWith('/plugin/')

  const listConfigFiles = async (
    scriptId: string,
    userId: string
  ): Promise<OkwwConfigListResponse> => {
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
    configsToUpdate: OkwwConfigPatchMap
  ): Promise<OkwwConfigUpdateResponse> => {
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
