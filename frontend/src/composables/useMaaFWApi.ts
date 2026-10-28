import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import { getAnalyticsScriptType } from '@/utils/analytics'
import { ref } from 'vue'
import { translate as t } from '@/i18n'
import { getApiErrorMessage } from '@/utils/apiError'
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
 * 后端端点是 `/api/scripts/maafw/asset`，与 `/maafw/preview`、`/maafw/update`
 * 同属脚本域。这里先拦掉绝对路径、UNC、上跳与远程 URL，但那只是省一次往返 ——
 * 安全边界在后端的 `_maafw_asset_file_path`。调用方对空串或加载失败均有降级处理
 * （`v-if` 或 `@error` 回退）。
 *
 * `/assets/x.png` 与 `{PROJECT_DIR}/x.png` 两种写法按项目根相对处理，与导入投影
 * （projection.py 的 `_normalize_ui_asset_path`）同一口径：投影会把这些文件带进副本，
 * 这里拒掉的话图标就显示不出来。
 */
export const buildMaaFWAssetUrl = (rootPath?: string | null, rawPath?: string | null) => {
  if (!rawPath || !rootPath) return ''
  const trimmed = rawPath.trim()
  if (/^(https?:|data:image\/)/i.test(trimmed)) return trimmed
  // UNC 只能在去开头斜杠之前认（去掉之后就像个相对路径）
  if (/^[\\/]{2}/.test(trimmed)) return ''

  const normalized = trimmed
    .replace(/\\/g, '/')
    .replace(/^\$\{PROJECT_DIR\}|^\{PROJECT_DIR\}/, '')
    .replace(/^\/+/, '')
    .replace(/^\.\/+/, '')
  // 盘符放在归一之后查：`/C:/x`、`{PROJECT_DIR}/C:/x` 去掉前缀后才露出盘符
  if (!normalized || /^[a-zA-Z]:/.test(normalized)) return ''
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
  snapshot: Partial<MaaFWTaskSnapshot> | null | undefined
): MaaFWTaskSnapshot => ({
  taskOrder: snapshot?.taskOrder ?? [],
  taskChecked: snapshot?.taskChecked ?? {},
  taskOptions: snapshot?.taskOptions ?? {},
  globalOptions: snapshot?.globalOptions ?? {},
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
      // PI v2 与后端模型的缺省值都是 true（默认展开）
      defaultExpand: group.defaultExpand ?? true,
    })),
    settings: (data.settings ?? []).map(setting => ({
      ...setting,
      option: setting.option ?? [],
      defaultExpand: setting.defaultExpand ?? true,
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
   * 带上 `scriptId` 时后端按脚本解析有效根：内嵌脚本读的是 AUTO-MAS 自己的副本，
   * 而不是 `path` 指向的来源目录；`path` 只在没有脚本 ID 时兜底。
   */
  const previewInterface = async (
    path: string,
    scriptId?: string
  ): Promise<MaaFWInterfacePreviewData | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await observeFeature(
        'adapter_setup_finished',
        {
          script_type: scriptId ? getAnalyticsScriptType(scriptId) : 'MaaFW',
          operation_kind: 'preview',
          engine_kind: 'unknown',
        },
        () =>
          MaaFwService.previewMaafwInterfaceApiScriptsMaafwPreviewPost({
            path,
            scriptId,
          }),
        apiOutcome
      )

      if (response.code !== 200 || !response.data) {
        throw new Error(response.message || t('core.apiErrors.maafwPreviewFailed'))
      }

      return normalizePreviewData(response.data as MaaFWInterfacePreviewData)
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('core.apiErrors.maafwPreviewFailed'))
      error.value = errorMsg
      logger.error(`读取项目 interface 失败: ${errorMsg}`)
      message.error(errorMsg)
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
