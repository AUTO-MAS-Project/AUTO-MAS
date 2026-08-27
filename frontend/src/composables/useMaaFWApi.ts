import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { MaaFwService, OpenAPI } from '@/api'
import type {
  MaaFWControlCapabilitiesInfo,
  MaaFWInterfacePreviewData,
  MaaFWOptionInfo,
  MaaFWPresetInfo,
  MaaFWTaskSnapshot,
} from '@/types/script'

const logger = window.electronAPI.getLogger('MaaFW接口')

/**
 * 拼接 MaaFW 项目内相对资源（图标、说明图片）的可访问 URL。
 *
 * 当前分支尚未迁移 `/api/maafw/asset` 资源代理端点，因此这里仍按回收版逻辑
 * 生成 URL；调用方对空串或加载失败均有降级处理（`v-if` 或 `@error` 回退）。
 */
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
  return `${baseUrl}/api/maafw/asset?${params.toString()}`
}

const normalizeTaskSnapshot = (
  snapshot: Partial<MaaFWTaskSnapshot> | null | undefined
): MaaFWTaskSnapshot => ({
  taskOrder: snapshot?.taskOrder ?? [],
  taskChecked: snapshot?.taskChecked ?? {},
  taskOptions: snapshot?.taskOptions ?? {},
})

const normalizeOption = (option: MaaFWOptionInfo): MaaFWOptionInfo => ({
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

const normalizePreset = (preset: MaaFWPresetInfo): MaaFWPresetInfo => ({
  ...preset,
  taskCount: preset.taskCount ?? 0,
  checkedCount: preset.checkedCount ?? 0,
  snapshot: normalizeTaskSnapshot(preset.snapshot),
})

type ApiMaaFWControlCapabilities = {
  controlCapabilities?: Partial<MaaFWControlCapabilitiesInfo> | null
}

const normalizeControlCapabilities = (
  data: MaaFWInterfacePreviewData & ApiMaaFWControlCapabilities
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

const normalizePreviewData = (data: MaaFWInterfacePreviewData): MaaFWInterfacePreviewData => {
  const rawData = data as MaaFWInterfacePreviewData & ApiMaaFWControlCapabilities
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
    settings: (data.settings ?? []).map(setting => ({
      ...setting,
      option: setting.option ?? [],
      defaultExpand: setting.defaultExpand ?? false,
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

export function useMaaFWApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * 读取 MaaFW 项目 interface，返回归一化后的预览数据。
   *
   * 回收版调用的是 `/api/maafw/interface/preview-script`（按 scriptId），当前分支
   * 复用 `app/api/scripts.py` 的 `POST /api/scripts/maafw/preview`（按 path），
   * 因此调用方需自行传入脚本的项目根目录。
   */
  const previewInterface = async (path: string): Promise<MaaFWInterfacePreviewData | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await MaaFwService.previewMaafwInterfaceApiScriptsMaafwPreviewPost({
        path,
      })

      if (response.code !== 200 || !response.data) {
        throw new Error(response.message || '读取 MaaFW interface 失败')
      }

      return normalizePreviewData(response.data as MaaFWInterfacePreviewData)
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

  return {
    loading,
    error,
    previewInterface,
  }
}
