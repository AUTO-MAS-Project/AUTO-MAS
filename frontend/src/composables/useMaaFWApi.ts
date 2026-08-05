import { ref } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import {
  MaaFwService,
  OpenAPI,
  type MaaFWInterfacePreviewData as ApiMaaFWInterfacePreviewData,
  type MaaFWTaskSnapshot as ApiMaaFWTaskSnapshot,
  type MaaFWWindowPreviewData as ApiMaaFWWindowPreviewData,
} from '@/api'
import type {
  MaaFWControlCapabilitiesInfo,
  MaaFWAgentEnvPrepareData,
  MaaFWInterfacePreviewData,
  MaaFWOptionInfo,
  MaaFWPresetInfo,
  MaaFWTaskSnapshot,
  MaaFWWindowPreviewData,
} from '@/types/script'

const logger = window.electronAPI.getLogger('MaaFW接口')

type PluginRouteEnvelope<T> = {
  code: number
  status: string
  message: string
  data: T | null
}

type MaaFWPluginProjectUpdateData = {
  checked: boolean
  updated: boolean
  updateAvailable?: boolean
  installable?: boolean
  currentVersion: string
  latestVersion?: string | null
  source?: string | null
  providerErrorCode?: number | null
  logs?: string[]
}

type MaaFWPluginAgentEnvPrepareData = {
  path: string
  agentCount?: number
  agents?: MaaFWAgentEnvPrepareData['agents']
  logs?: string[]
  status?: string
  message?: string
}

const MAAFW_PLUGIN_ROUTE_PREFIX = '/maafw'

const resolvePluginRouteUrl = (path: string): string => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const baseUrl = (OpenAPI.BASE || '').replace(/\/+$/, '')
  return `${baseUrl}/plugin${normalizedPath}`
}

type PluginHttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS'

const requestPluginRoute = async <T>(
  path: string,
  payload: Record<string, unknown> = {},
  method: PluginHttpMethod = 'POST'
): Promise<PluginRouteEnvelope<T>> => {
  try {
    const response = await axios.request<PluginRouteEnvelope<T>>({
      method,
      url: resolvePluginRouteUrl(path),
      params: method === 'GET' ? payload : undefined,
      data: method === 'GET' ? undefined : payload,
    })
    return response.data
  } catch (error) {
    if (axios.isAxiosError<PluginRouteEnvelope<T>>(error) && error.response?.data) {
      return error.response.data
    }
    throw error
  }
}

export const buildMaaFWAssetUrl = (rootPath?: string, rawPath?: string | null) => {
  if (!rawPath || !rootPath) return ''
  if (/^(https?:|data:image\/)/i.test(rawPath)) return rawPath
  if (/^[a-zA-Z]:[\\/]/.test(rawPath) || rawPath.startsWith('/') || rawPath.startsWith('\\\\')) {
    return ''
  }

  const normalized = rawPath.replace(/\\/g, '/').replace(/^\.\/+/, '')
  if (normalized === '..' || normalized.startsWith('../') || normalized.includes('/../')) {
    return ''
  }

  const baseUrl = OpenAPI.BASE || 'http://localhost:36163'
  const params = new URLSearchParams({
    root: rootPath,
    path: normalized,
  })
  return `${baseUrl}/api/scripts/maafw/asset?${params.toString()}`
}

const normalizeTaskSnapshot = (
  snapshot: ApiMaaFWTaskSnapshot | null | undefined
): MaaFWTaskSnapshot => ({
  taskOrder: snapshot?.taskOrder ?? [],
  taskChecked: snapshot?.taskChecked ?? {},
  taskOptions: snapshot?.taskOptions ?? {},
})

const normalizeOption = (
  option: NonNullable<ApiMaaFWInterfacePreviewData['options']>[number]
): MaaFWOptionInfo => ({
  ...option,
  controller: option.controller ?? [],
  resource: option.resource ?? [],
  icon: (option as typeof option & { icon?: string | null }).icon ?? null,
  cases: (option.cases ?? []).map(optionCase => ({
    ...optionCase,
    icon: (optionCase as typeof optionCase & { icon?: string | null }).icon ?? null,
    option: optionCase.option ?? [],
  })),
  inputs: (option.inputs ?? []).map(inputItem => {
    const rawInput = inputItem as typeof inputItem & {
      icon?: string | null
      verifyError?: string | null
    }
    return {
      ...inputItem,
      icon: rawInput.icon ?? null,
      verifyError: rawInput.verifyError ?? inputItem.patternMsg ?? null,
    }
  }),
})

const normalizePreset = (
  preset: NonNullable<ApiMaaFWInterfacePreviewData['presets']>[number]
): MaaFWPresetInfo => ({
  ...preset,
  taskCount: preset.taskCount ?? 0,
  checkedCount: preset.checkedCount ?? 0,
  snapshot: normalizeTaskSnapshot(preset.snapshot),
})

type ApiMaaFWControlCapabilities = {
  controlCapabilities?: Partial<MaaFWControlCapabilitiesInfo> | null
}

const normalizeControlCapabilities = (
  data: ApiMaaFWInterfacePreviewData & ApiMaaFWControlCapabilities
): MaaFWControlCapabilitiesInfo => ({
  emulatorExtras: Object.fromEntries(
    Object.entries(data.controlCapabilities?.emulatorExtras ?? {}).map(
      ([emulatorType, capability]) => [
        emulatorType,
        {
          screencap: Boolean(capability?.screencap),
          input: Boolean(capability?.input),
        },
      ]
    )
  ),
})

const normalizePreviewData = (data: ApiMaaFWInterfacePreviewData): MaaFWInterfacePreviewData => {
  const rawData = data as ApiMaaFWInterfacePreviewData & ApiMaaFWControlCapabilities
  return {
    path: data.path,
    project: data.project,
    globalOption: data.globalOption ?? [],
    controlCapabilities: normalizeControlCapabilities(rawData),
    controllers: (data.controllers ?? []).map(controller => ({
      ...controller,
      option: controller.option ?? [],
      permissionRequired: controller.permissionRequired ?? false,
    })),
    resources: (data.resources ?? []).map(resource => ({
      ...resource,
      path: resource.path ?? [],
      controller: resource.controller ?? [],
      option: resource.option ?? [],
    })),
    groups: (data.groups ?? []).map(group => ({
      ...group,
      defaultExpand: group.defaultExpand ?? false,
    })),
    tasks: (data.tasks ?? []).map(task => ({
      ...task,
      icon: (task as typeof task & { icon?: string | null }).icon ?? null,
      group: task.group ?? [],
      controller: task.controller ?? [],
      resource: task.resource ?? [],
      option: task.option ?? [],
      defaultCheck: task.defaultCheck ?? false,
    })),
    options: (data.options ?? []).map(normalizeOption),
    presets: (data.presets ?? []).map(normalizePreset),
    importCount: data.importCount ?? 0,
    agentCount: data.agentCount ?? 0,
  }
}

const normalizeWindowPreviewData = (data: ApiMaaFWWindowPreviewData): MaaFWWindowPreviewData => ({
  path: data.path,
  controllerName: data.controllerName,
  windows: (data.windows ?? []).map(window => ({
    hWnd: window.hWnd,
    className: window.className ?? '',
    windowName: window.windowName ?? '',
    controllerName: window.controllerName,
    controllerType: window.controllerType,
  })),
})

const normalizeAgentEnvPrepareData = (
  data: MaaFWPluginAgentEnvPrepareData,
  status?: string,
  responseMessage?: string
): MaaFWAgentEnvPrepareData => ({
  path: data.path,
  agentCount: data.agentCount ?? 0,
  agents: data.agents ?? [],
  logs: data.logs ?? [],
  status: status || data.status,
  message: responseMessage || data.message,
})

export function useMaaFWApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const previewInterface = async (path: string): Promise<MaaFWInterfacePreviewData | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await MaaFwService.previewMaafwInterfaceApiScriptsMaafwInterfacePreviewPost({
        path,
      })

      if (response.code !== 200 || !response.data) {
        const errorMsg = response.message || '读取 MaaFW interface 失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return normalizePreviewData(response.data)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '读取 MaaFW interface 失败'
      error.value = errorMsg
      logger.error(`读取 MaaFW interface 失败: ${errorMsg}`)
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  const previewWindows = async (
    path: string,
    controllerName?: string
  ): Promise<MaaFWWindowPreviewData | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await MaaFwService.previewMaafwWindowsApiScriptsMaafwWindowsPreviewPost({
        path,
        controllerName: controllerName || null,
      })

      if (response.code !== 200 || !response.data) {
        const errorMsg = response.message || '扫描 MaaFW PC 客户端窗口失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return normalizeWindowPreviewData(response.data)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '扫描 MaaFW PC 客户端窗口失败'
      error.value = errorMsg
      logger.error(`扫描 MaaFW PC 客户端窗口失败: ${errorMsg}`)
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  const prepareAgentEnv = async (
    path: string,
    scriptId?: string
  ): Promise<MaaFWAgentEnvPrepareData | null> => {
    loading.value = true
    error.value = null

    try {
      const payload: Record<string, unknown> = { path }
      if (scriptId) payload.scriptId = scriptId
      const response = await requestPluginRoute<MaaFWPluginAgentEnvPrepareData>(
        `${MAAFW_PLUGIN_ROUTE_PREFIX}/agent-env/prepare`,
        payload
      )

      if (response.code !== 200 || !response.data) {
        const errorMsg = response.message || '准备 MaaFW 运行环境失败'
        message.error(errorMsg)
        if (response.data) {
          error.value = errorMsg
          return normalizeAgentEnvPrepareData(response.data, response.status, response.message)
        }
        throw new Error(errorMsg)
      }

      return normalizeAgentEnvPrepareData(response.data, response.status, response.message)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '准备 MaaFW 运行环境失败'
      error.value = errorMsg
      logger.error(`准备 MaaFW 运行环境失败: ${errorMsg}`)
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  const updateProjectResources = async (
    scriptId: string,
    apply = false
  ): Promise<PluginRouteEnvelope<MaaFWPluginProjectUpdateData> | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await requestPluginRoute<MaaFWPluginProjectUpdateData>(
        `${MAAFW_PLUGIN_ROUTE_PREFIX}/project/update`,
        { scriptId, apply }
      )

      if (response.code !== 200) {
        const errorMsg = response.message || 'MaaFW 项目更新失败'
        error.value = errorMsg
        message.error(errorMsg)
        return response
      }

      return response
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'MaaFW 项目更新失败'
      error.value = errorMsg
      logger.error(`MaaFW 项目更新失败: ${errorMsg}`)
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    previewInterface,
    previewWindows,
    prepareAgentEnv,
    updateProjectResources,
  }
}
