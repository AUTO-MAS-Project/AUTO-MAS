import { computed, onScopeDispose, ref, type Ref } from 'vue'
import { GetService } from '@/api'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
import { WS_MAAFW_PROJECT_UPDATE_PROGRESS } from '@/services/websocket/types'
import { useMaaFWUpdateApi, type MaaFWUpdateResult } from '@/composables/useMaaFWUpdateApi'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'
import {
  createUpdateProgressState,
  finishUpdateProgress,
  reduceUpdateProgress,
  type MaaFWUpdateProgressState,
} from './updateProgress'
import type { MaaFWScriptChangeHandler } from './useMaaFWScriptDraft'

interface MaaFWUpdatePanelOptions {
  scriptId: string
  maafwConfig: MaaFWScriptConfig
  previewData: Ref<MaaFWInterfacePreviewData | null>
  handleChange: MaaFWScriptChangeHandler
  /** 更新真的换了文件之后重新读 interface */
  runPreview: () => Promise<void>
}

/** 「项目更新」区块：检查 / 应用更新、过程订阅，以及 Mirror 酱 CDK 预填。 */
export function useMaaFWUpdatePanel({
  scriptId,
  maafwConfig,
  previewData,
  handleChange,
  runPreview,
}: MaaFWUpdatePanelOptions) {
  const logger = window.electronAPI.getLogger('MaaFW 脚本编辑')
  const { checkMaaFWUpdate, applyMaaFWUpdate } = useMaaFWUpdateApi()

  const isAutoUpdateDisabled = computed(() =>
    Boolean(previewData.value && !previewData.value.project.version)
  )

  // 手动更新过程（检查 / 下载 / 覆盖 / 校验 + 逐行日志）同样由后端推过来，
  // 折叠成一份面板状态交给「项目更新」区块显示。
  const updateProgress = ref<MaaFWUpdateProgressState>(createUpdateProgressState())
  let updateSubscriptionId: string | null = null

  const ensureUpdateSubscription = () => {
    if (updateSubscriptionId) return
    updateSubscriptionId = subscribe(
      { id: scriptId, type: WS_MAAFW_PROJECT_UPDATE_PROGRESS },
      wsMessage => {
        updateProgress.value = reduceUpdateProgress(updateProgress.value, wsMessage.data)
      }
    )
  }

  onScopeDispose(() => {
    if (updateSubscriptionId) {
      unsubscribe(updateSubscriptionId)
      updateSubscriptionId = null
    }
  })

  const updateChecking = ref(false)
  const updateApplying = ref(false)
  const updateError = ref('')
  const updateResult = ref<MaaFWUpdateResult | null>(null)

  // 每次点「检查更新」或「更新」都从头显示过程；订阅要在请求发出前就挂上，
  // 否则后端最先推的那几条（检查中 / 首行日志）会漏掉。
  const beginUpdateProgress = () => {
    ensureUpdateSubscription()
    updateProgress.value = createUpdateProgressState('checking')
  }

  // HTTP 响应回来后兜底收尾：WS 断连时面板也要能落到终态，
  // 已由 WS 收尾的不改（后端那句更具体）。
  const settleUpdateProgress = (success: boolean, text: string) => {
    updateProgress.value = finishUpdateProgress(updateProgress.value, { success, message: text })
  }

  const runUpdateCheck = async () => {
    updateChecking.value = true
    updateError.value = ''
    beginUpdateProgress()
    try {
      updateResult.value = await checkMaaFWUpdate(scriptId)
      settleUpdateProgress(true, updateResult.value.message)
    } catch (error) {
      updateResult.value = null
      updateError.value = error instanceof Error ? error.message : String(error)
      settleUpdateProgress(false, updateError.value)
    } finally {
      updateChecking.value = false
    }
  }

  const runUpdateApply = async () => {
    updateApplying.value = true
    updateError.value = ''
    beginUpdateProgress()
    try {
      updateResult.value = await applyMaaFWUpdate(scriptId)
      settleUpdateProgress(true, updateResult.value.message)
      if (updateResult.value.updated && maafwConfig.Info.Path) {
        await runPreview()
      }
    } catch (error) {
      updateError.value = error instanceof Error ? error.message : String(error)
      settleUpdateProgress(false, updateError.value)
    } finally {
      updateApplying.value = false
    }
  }

  // Mirror 酱 CDK：脚本级为空时把 MAS 更新设置里填过的那份直接填进来并落盘，
  // 用户不用在两处各填一遍。已填过的脚本一律不动；后端仍只看脚本级配置。
  const cdkPrefilled = ref(false)

  const prefillMirrorChyanCdk = async () => {
    if (maafwConfig.Update.MirrorChyanCDK.trim()) return
    try {
      // 直接调生成的客户端而不是 useSettingsApi().getSettings()：后者失败时会弹
      // 「获取设置失败」的红色提示，与本页无关，预填只是锦上添花，静默跳过即可。
      const response = await GetService.getScriptsApiSettingGetPost()
      if (response.code !== 200) return
      const globalCdk = (response.data?.Update?.MirrorChyanCDK ?? '').trim()
      // 等待期间用户可能已经自己敲进去了，再查一次
      if (!globalCdk || maafwConfig.Update.MirrorChyanCDK.trim()) return
      maafwConfig.Update.MirrorChyanCDK = globalCdk
      cdkPrefilled.value = true
      await handleChange('Update', 'MirrorChyanCDK', globalCdk)
    } catch (error) {
      logger.warn(`读取全局 CDK 失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  return {
    isAutoUpdateDisabled,
    updateChecking,
    updateApplying,
    updateError,
    updateResult,
    updateProgress,
    runUpdateCheck,
    runUpdateApply,
    cdkPrefilled,
    prefillMirrorChyanCdk,
  }
}
