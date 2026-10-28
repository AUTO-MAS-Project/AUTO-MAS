import { computed, onScopeDispose, ref, type Ref } from 'vue'
import { GetService } from '@/api'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
import { WS_MAAFW_PROJECT_UPDATE_PROGRESS } from '@/services/websocket/types'
import {
  useMaaFWUpdateApi,
  type MaaFWUpdateJobSnapshot,
  type MaaFWUpdateResult,
} from '@/composables/useMaaFWUpdateApi'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'
import type { WSMaaFWProjectUpdateProgressData } from '@/services/websocket/types'
import {
  createUpdateProgressState,
  finishUpdateProgress,
  reduceUpdateProgress,
  replayUpdateProgress,
  type MaaFWUpdateProgressState,
} from './updateProgress'
import type { MaaFWScriptChangeHandler } from './useMaaFWScriptDraft'

// 手动更新的结果在这台机器上显示过一次就不再接回：后端把最近一次结果留到下次更新或重启，
// 不记的话几小时前的一条失败每次打开编辑页都会标红。按脚本记最后显示过的那次的开始时刻，
// 与「添加任务」的 NEW 一样只是本机提示状态，存在 localStorage，不进配置。
const seenUpdateStorageKey = (scriptId: string) => `maafw-seen-update:${scriptId}`

const readSeenUpdate = (scriptId: string): string | null => {
  try {
    return localStorage.getItem(seenUpdateStorageKey(scriptId))
  } catch {
    return null
  }
}

const markUpdateSeen = (scriptId: string, startedAt: string) => {
  if (!startedAt) return
  try {
    localStorage.setItem(seenUpdateStorageKey(scriptId), startedAt)
  } catch {
    // 本机存不下只是下次打开会再显示一遍
  }
}

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
  const { checkMaaFWUpdate, applyMaaFWUpdate, getMaaFWUpdateJob } = useMaaFWUpdateApi()

  // 与后端 can_check_project_update 同一口径：没声明 version 判断不了新旧；没有
  // mirrorchyan_rid 时，只有下载源选 GitHub、interface 又声明了 github 仓库才查得到版本
  // （只看 GitHub Release）。查不到的情况自动更新都不会发生
  const isAutoUpdateDisabled = computed(() => {
    const project = previewData.value?.project
    if (!project) return false
    if (!project.version) return true
    if (project.mirrorchyanRid?.trim()) return false
    return !(maafwConfig.Update.Source === 'GitHub' && project.github?.trim())
  })

  // 手动更新过程（检查 / 下载 / 覆盖 / 校验 + 逐行日志）同样由后端推过来，
  // 折叠成一份面板状态交给「项目更新」区块显示。
  const updateProgress = ref<MaaFWUpdateProgressState>(createUpdateProgressState())
  let updateSubscriptionId: string | null = null
  // 接回后台更新时，取快照期间到的推送先攒在这里，快照回来后再接上
  let pendingEvents: WSMaaFWProjectUpdateProgressData[] | null = null
  // 每次从头显示过程（点检查 / 更新、接回）加一；晚回来的接回结果按它丢掉
  let progressSession = 0
  let disposed = false

  const ensureUpdateSubscription = () => {
    if (updateSubscriptionId) return
    updateSubscriptionId = subscribe(
      { id: scriptId, type: WS_MAAFW_PROJECT_UPDATE_PROGRESS },
      wsMessage => {
        if (pendingEvents) {
          pendingEvents.push(wsMessage.data)
          return
        }
        updateProgress.value = reduceUpdateProgress(updateProgress.value, wsMessage.data)
      }
    )
  }

  onScopeDispose(() => {
    disposed = true
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
    progressSession += 1
    pendingEvents = null
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
    // 结果已经在这一页上显示了：记下这一次，之后再打开不必接回
    await rememberShownUpdate()
  }

  const rememberShownUpdate = async () => {
    try {
      const snapshot = await getMaaFWUpdateJob(scriptId)
      if (snapshot.state === 'finished') markUpdateSeen(scriptId, snapshot.startedAt)
    } catch {
      // 查不到只是下次打开会再显示一遍
    }
  }

  // 手动更新在后端后台跑，切走页面、刷新、关掉前端都不打断。页面打开时接回这个脚本当前或
  // 最近一次手动更新：先挂订阅（推送先攒着）再取快照，重放出面板后接上攒下的推送；
  // 还在跑就等它结束取结果，与自己点「更新」时收尾一样。
  const resumeManualUpdate = async () => {
    if (updateChecking.value || updateApplying.value) return
    const session = ++progressSession
    const isStale = () => disposed || session !== progressSession
    pendingEvents = []
    ensureUpdateSubscription()
    let snapshot: MaaFWUpdateJobSnapshot
    try {
      snapshot = await getMaaFWUpdateJob(scriptId)
    } catch (error) {
      if (!isStale()) pendingEvents = null
      logger.warn(`查询手动更新状态失败: ${error instanceof Error ? error.message : String(error)}`)
      return
    }
    if (isStale()) return
    const pending = pendingEvents ?? []
    pendingEvents = null
    if (snapshot.state === 'idle') return
    if (snapshot.state === 'finished' && readSeenUpdate(scriptId) === snapshot.startedAt) return
    logger.info(
      `接回手动更新: state=${snapshot.state} 已有事件 ${snapshot.events.length} 条，取快照期间推送 ${pending.length} 条`
    )
    updateProgress.value = replayUpdateProgress(
      snapshot.events,
      snapshot.state === 'running' ? pending : []
    )
    // 打开页面时已经结束的，页面加载本来就会读一次 interface；等到结束的才要重读
    const waited = snapshot.state === 'running'
    if (waited) {
      updateApplying.value = true
      updateError.value = ''
      try {
        snapshot = await getMaaFWUpdateJob(scriptId, true)
      } catch (error) {
        if (isStale()) return
        updateApplying.value = false
        updateError.value = error instanceof Error ? error.message : String(error)
        settleUpdateProgress(false, updateError.value)
        return
      }
      if (isStale()) return
      updateApplying.value = false
    }
    if (snapshot.result) {
      updateResult.value = snapshot.result
      updateError.value = ''
      settleUpdateProgress(true, snapshot.result.message)
      markUpdateSeen(scriptId, snapshot.startedAt)
      if (waited && snapshot.result.updated && maafwConfig.Info.Path) {
        await runPreview()
      }
    } else if (snapshot.error) {
      updateError.value = snapshot.error
      settleUpdateProgress(false, snapshot.error)
      markUpdateSeen(scriptId, snapshot.startedAt)
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
    resumeManualUpdate,
    cdkPrefilled,
    prefillMirrorChyanCdk,
  }
}
