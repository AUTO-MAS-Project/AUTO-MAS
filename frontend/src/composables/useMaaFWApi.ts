import { ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  MaaFwService,
  OpenAPI,
  type MaaFWInterfacePreviewData as ApiMaaFWInterfacePreviewData,
  type MaaFWProjectUpdateOut as ApiMaaFWProjectUpdateOut,
  type MaaFWTaskSnapshot as ApiMaaFWTaskSnapshot,
  type MaaFWWindowPreviewData as ApiMaaFWWindowPreviewData,
} from '@/api'
import { request as apiRequest } from '@/api/core/request'
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
  data: MaaFWAgentEnvPrepareData,
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

type MaaFWAgentEnvPrepareOut = {
  code?: number
  status?: string
  message?: string
  data?: MaaFWAgentEnvPrepareData | null
}

type MaaFWRequestLifecycle = {
  isActive?: () => boolean
  notify?: boolean
}

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
    scriptId?: string,
    lifecycle?: MaaFWRequestLifecycle
  ): Promise<MaaFWAgentEnvPrepareData | null> => {
    const isActive = () => lifecycle?.isActive?.() ?? true
    const shouldNotify = () => lifecycle?.notify !== false && isActive()
    if (!isActive()) return null

    loading.value = true
    error.value = null

    try {
      const response = await apiRequest<MaaFWAgentEnvPrepareOut>(OpenAPI, {
        method: 'POST',
        url: '/api/scripts/maafw/agent-env/prepare',
        body: { path, scriptId },
        headers: scriptId ? { 'X-MaaFW-Progress-Id': scriptId } : undefined,
        mediaType: 'application/json',
        errors: {
          422: 'Validation Error',
        },
      })

      if (response.code !== 200 || !response.data) {
        const errorMsg = response.message || '准备 MaaFW 运行环境失败'
        if (shouldNotify()) message.error(errorMsg)
        if (response.data) {
          if (isActive()) error.value = errorMsg
          return normalizeAgentEnvPrepareData(response.data, response.status, response.message)
        }
        throw new Error(errorMsg)
      }

      return normalizeAgentEnvPrepareData(response.data, response.status, response.message)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '准备 MaaFW 运行环境失败'
      if (isActive()) error.value = errorMsg
      logger.error(`准备 MaaFW 运行环境失败: ${errorMsg}`)
      if (shouldNotify() && err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      if (isActive()) loading.value = false
    }
  }

  const updateProjectResources = async (
    scriptId: string
  ): Promise<ApiMaaFWProjectUpdateOut | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await MaaFwService.updateMaafwProjectApiScriptsMaafwProjectUpdatePost({
        scriptId,
      })

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
