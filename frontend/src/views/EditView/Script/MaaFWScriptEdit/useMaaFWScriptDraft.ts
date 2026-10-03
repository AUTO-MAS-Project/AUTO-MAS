import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useScriptApi } from '@/composables/useScriptApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import {
  getDefaultMaaFWScriptConfig,
  isMaaFWUpdateChannel,
  isMaaFWUpdateSource,
} from '@/composables/useMaaFWScriptConfig'
import { resolveAutoUpdateMode } from '@/composables/useMaaFWProjectUpdate'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig, ScriptType } from '@/types/script'

export type MaaFWScriptFormData = { type: ScriptType; name: string; path: string }

export type MaaFWScriptChangeHandler = (
  category: keyof MaaFWScriptConfig,
  key: string,
  value: unknown
) => Promise<void>

/**
 * MFW 脚本页的配置草稿：本地配置、表单、interface 预览数据、初始化闸门与串行保存。
 *
 * `handleChange` 在 `isInitializing` 为 true 时不落盘：加载期间同步出来的值只改草稿，
 * 由编排层在初始化结束后再补写需要落盘的项。
 */
export function useMaaFWScriptDraft(scriptId: string) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MaaFW 脚本编辑')
  const { updateScript } = useScriptApi()

  const pageLoading = ref(false)
  const isInitializing = ref(true)
  // 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
  const { enqueue } = useSaveQueue()

  const previewLoading = ref(false)
  const previewData = ref<MaaFWInterfacePreviewData | null>(null)

  const maafwConfig = reactive<MaaFWScriptConfig>(getDefaultMaaFWScriptConfig())

  const formData = reactive<MaaFWScriptFormData>({
    type: 'MaaFW',
    name: '',
    path: '',
  })

  const rules = {
    name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
    path: [
      {
        validator: () =>
          maafwConfig.Info.Path
            ? Promise.resolve()
            : Promise.reject(new Error('请选择 MFW 项目实际目录并读取 interface')),
        trigger: 'blur',
      },
    ],
  }

  const handleChange: MaaFWScriptChangeHandler = async (category, key, value) => {
    if (isInitializing.value) return
    await enqueue(
      async () => {
        try {
          const success = await updateScript(scriptId, { [category]: { [key]: value } })
          if (success) logger.info(`配置已保存: ${String(category)}.${key}`)
        } catch (error) {
          logger.error(`保存失败: ${error instanceof Error ? error.message : String(error)}`)
        }
      },
      `${String(category)}.${key}`
    )
  }

  /**
   * 把后端配置铺到草稿上（缺的分区与字段取默认值）。只铺草稿，不管周期任务的三个本地列表：
   * 页面上一律走编排层 useMaaFWScriptPage 的 `applyScriptConfig`，它铺完草稿紧接着同步周期任务。
   */
  const applyScriptConfig = (config: Partial<MaaFWScriptConfig> | null | undefined) => {
    const defaults = getDefaultMaaFWScriptConfig()
    ;(Object.keys(defaults) as Array<keyof MaaFWScriptConfig>).forEach(section => {
      Object.assign(
        maafwConfig[section] as Record<string, unknown>,
        defaults[section] as Record<string, unknown>,
        (config?.[section] as Record<string, unknown>) ?? {}
      )
    })
    // 旧配置只有 IfAutoUpdate 时映射到新的自动更新时机；只改本地草稿，不回写后端。
    maafwConfig.Update.AutoUpdateMode = resolveAutoUpdateMode(config?.Update)
    // 旧配置里 Source / Channel 可能是空串（曾表示「自动」/「跟随全局」），现在都不是
    // 合法选项，下拉框会显示空白；同样只修正本地草稿，用户改动前不回写。
    if (!isMaaFWUpdateSource(maafwConfig.Update.Source)) {
      maafwConfig.Update.Source = defaults.Update.Source
    }
    if (!isMaaFWUpdateChannel(maafwConfig.Update.Channel)) {
      maafwConfig.Update.Channel = defaults.Update.Channel
    }
    formData.name = maafwConfig.Info.Name || ''
    formData.path = maafwConfig.Info.Path || ''
  }

  return {
    pageLoading,
    isInitializing,
    enqueue,
    previewLoading,
    previewData,
    maafwConfig,
    formData,
    rules,
    handleChange,
    applyScriptConfig,
  }
}

export type MaaFWScriptDraft = ReturnType<typeof useMaaFWScriptDraft>
