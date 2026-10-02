import { computed, h, ref, watch, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { message } from 'ant-design-vue'
import type { MaaFWShellInstanceItem } from '@/api'
import { useMaaFWShellInstanceApi } from '@/composables/useMaaFWShellInstanceApi'
import type { MaaFWFlavor } from '@/composables/useMaaFWFlavor'
import { maafwRouteLocation } from '@/router/maafwFlavorRoutes'
import type { MaaFWPageHostContext } from '../../MaaFWFlavor/pageHostContext'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'
import {
  buildShellImportReportLines,
  shellImportItemName,
  summarizeShellImport,
  type ShellImportSummary,
} from './shellInstanceImport'
import { parseHotkeyMap } from './hotkeyOptions'
import {
  allHotkeyOptions,
  collectHotkeyImportCandidates,
  mergeImportedHotkeys,
} from './hotkeyImport'
import type { MaaFWScriptChangeHandler } from './useMaaFWScriptDraft'

interface MaaFWSetupWizardOptions {
  scriptId: string
  previewData: Ref<MaaFWInterfacePreviewData | null>
  /** 脚本配置草稿：「同时把键位导入到脚本」改 Game.Hotkeys */
  maafwConfig: MaaFWScriptConfig
  /** 页面的配置保存通道 */
  handleChange: MaaFWScriptChangeHandler
  envReady: Ref<boolean>
  enqueue: <T>(run: () => Promise<T>, key?: string) => Promise<T>
  flavor: ComputedRef<MaaFWFlavor>
  /** 页面宿主的上下文：页面种类与引导步骤取它的；不在宿主里为 null（按路由 meta） */
  host: MaaFWPageHostContext | null
  /** 页面已卸载：还在跑的异步流程（外壳配置导入）结束时不再跳转 */
  isPageUnmounted: () => boolean
}

/** 引导形态：步骤、能否离开当前步、最后一步的外壳实例导入与「完成」跳转。 */
export function useMaaFWSetupWizard({
  scriptId,
  previewData,
  maafwConfig,
  handleChange,
  envReady,
  enqueue,
  flavor,
  host,
  isPageUnmounted,
}: MaaFWSetupWizardOptions) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MaaFW 脚本编辑')
  const route = useRoute()
  const router = useRouter()
  const { listShellInstances, importShellInstances } = useMaaFWShellInstanceApi()

  // 引导模式：同一个页面按步骤渲染四个分节。新建 MaaFW 家族脚本后进引导路由（页面种类 setup），
  // 之后再编辑走编辑路由的完整单页形态。
  const mode = host ? host.mode : route.meta.maafwPage
  const isWizard = computed(() => mode === 'setup')
  // 步骤放在宿主里：导入后类型变了、宿主换成特调自己的页面时，新页面接着这一步走
  const currentStep = host?.wizardStep ?? ref(0)
  const stepItems = [
    { title: t('edit.basicInfo') },
    { title: t('edit.controlConfiguration') },
    { title: t('edit.projectUpdate') },
    { title: t('edit.runConfiguration') },
  ]
  // 第一步没读到 interface 就往下走，后面几步全是空的，先拦住。
  // 运行环境同理：没装完就往下配，配完了也跑不起来——首次要下载 MaaFramework，
  // 失败时（离线、镜像不通、解释器坏）后面每一步都是白填。失败不是死路，
  // 提示条里有「重试」。
  const canLeaveCurrentStep = computed(
    () => currentStep.value !== 0 || (previewData.value !== null && envReady.value)
  )

  // 用户页路由按脚本当前类型走对应那条线
  const addUserLocation = () => maafwRouteLocation(flavor.value.type, 'userAdd', { scriptId })

  // 引导最后一步直接去建第一个用户；先等排队中的保存写完，用户页读到的才是刚配好的脚本
  const handleCreateFirstUser = async () => {
    await enqueue(async () => undefined)
    router.push(addUserLocation())
  }

  // ---- 引导最后一步：外壳（MFAAvalonia / MXU / MFW-PyQt6）配置导入成用户 ----
  // 只在引导形态、进入最后一步时扫描；扫不到或扫描失败都只记日志，区块不显示。
  const shellInstances = ref<MaaFWShellInstanceItem[]>([])
  const selectedShellInstanceIds = ref<string[]>([])
  // 「同时把键位导入到脚本」：选中的实例里有带键位的才显示，默认开
  const importShellHotkeys = ref(true)
  const shellImporting = ref(false)

  const loadShellInstances = async () => {
    try {
      const list = await listShellInstances(scriptId)
      // 回到这一步时保留用户之前的勾选；新出现的实例默认勾上
      const previous = new Set(shellInstances.value.map(item => item.id))
      const selected = new Set(selectedShellInstanceIds.value)
      shellInstances.value = list
      selectedShellInstanceIds.value = list
        .filter(item => !previous.has(item.id) || selected.has(item.id))
        .map(item => item.id)
    } catch (error) {
      shellInstances.value = []
      selectedShellInstanceIds.value = []
      logger.warn(`扫描外壳配置失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  watch(
    () => isWizard.value && currentStep.value === stepItems.length - 1,
    onLastStep => {
      if (onLastStep) void loadShellInstances()
    }
  )

  const finishButtonLabel = computed(() => {
    if (shellImporting.value) return t('edit.shellImporting')
    const count = selectedShellInstanceIds.value.length
    return count > 0 ? t('edit.shellImportButton', { count }) : t('edit.createFirstUser')
  })

  // 导入要一会儿，结束时用户可能已经离开了这一页（面包屑等）：那时只弹提示、不跳转，
  // 免得把人从别的页面拽回来（pageUnmounted 在卸载钩子里置位）
  const stillOnWizard = () =>
    !isPageUnmounted() && route.meta.maafwPage === 'setup' && route.params.id === scriptId
  const leaveWizardTo = (target: RouteLocationRaw) => {
    if (stillOnWizard()) router.push(target)
  }

  // 选中的实例带着键位、开关开着：取一份（外壳上次使用的优先，否则按选中顺序第一份）并进
  // Game.Hotkeys，只存与默认不同的字段、脚本已有的其他条目保留；草稿同步改，之后打开弹窗看到的是新值。
  // 不影响用户任务快照里的键位（那条路由导入用户照旧写）。
  const importHotkeysToScript = async (instanceIds: readonly string[]) => {
    if (!importShellHotkeys.value) return
    const selected = new Set(instanceIds)
    const options = allHotkeyOptions(previewData.value)
    // 与键位弹窗「从项目导入」同一套候选：外壳上次使用的那份优先，否则按选中顺序第一份
    const hotkeys = collectHotkeyImportCandidates(
      shellInstances.value.filter(item => selected.has(item.id)),
      options
    )[0]?.hotkeys
    if (!hotkeys) return
    const existing = parseHotkeyMap(maafwConfig.Game.Hotkeys)
    const next = JSON.stringify(mergeImportedHotkeys(existing, options, hotkeys))
    if (next === JSON.stringify(existing)) return
    maafwConfig.Game.Hotkeys = next
    await handleChange('Game', 'Hotkeys', next)
    logger.info(`已把外壳配置里的键位写进脚本: ${next}`)
  }

  // 勾了实例就导入，一个都没勾就是原来的「创建第一个用户！」。导入失败不能把用户卡在引导页：
  // 一个用户都没建成就报错并退回建空用户；部分失败 / 导不全合并成一条提示，照常往下走。
  const handleFinishWizard = async () => {
    const instanceIds = [...selectedShellInstanceIds.value]
    if (instanceIds.length === 0) {
      await handleCreateFirstUser()
      return
    }
    // 结果项里没带实例名时（找不到的实例）按列表里的名字写，都没有才退回 ID
    const instanceNames = new Map(shellInstances.value.map(item => [item.id, item.name]))
    shellImporting.value = true
    try {
      // 先写键位再建用户：建用户之后要跳页，键位放在前面与页面同生命周期；它走同一个保存队列，
      // 下面那次排空会等它落盘。键位写不进去只记日志，不挡导入用户。
      try {
        await importHotkeysToScript(instanceIds)
      } catch (error) {
        logger.warn(
          `把外壳配置的键位写进脚本失败: ${error instanceof Error ? error.message : String(error)}`
        )
      }
      await enqueue(async () => undefined)
      let summary: ShellImportSummary
      try {
        summary = summarizeShellImport(await importShellInstances(scriptId, instanceIds))
      } catch (error) {
        const reason = error instanceof Error ? error.message : String(error)
        logger.error(`导入外壳配置失败: ${reason}`)
        message.error(t('edit.shellImportAllFailedWithReason', { reason }))
        leaveWizardTo(addUserLocation())
        return
      }
      for (const item of [...summary.failed, ...summary.partial]) {
        logger.warn(
          `导入外壳配置「${shellImportItemName(item, instanceNames)}」：` +
            (item.error ? `失败 ${item.error}` : `跳过 ${(item.skipped ?? []).join('、')}`)
        )
      }
      const lines = buildShellImportReportLines(summary, t, instanceNames)
      if (summary.created.length === 0) {
        message.error({
          content: h(
            'div',
            [t('edit.shellImportAllFailed'), ...lines].map(line => h('div', line))
          ),
          duration: 8,
        })
        leaveWizardTo(addUserLocation())
        return
      }
      if (lines.length > 0) {
        const notify = summary.failed.length > 0 ? message.error : message.warning
        notify({
          content: h(
            'div',
            lines.map(line => h('div', line))
          ),
          duration: 8,
        })
      }
      const [only] = summary.created
      leaveWizardTo(
        summary.created.length === 1 && only.userId
          ? maafwRouteLocation(flavor.value.type, 'userEdit', { scriptId, userId: only.userId })
          : '/scripts'
      )
    } finally {
      shellImporting.value = false
    }
  }

  return {
    isWizard,
    currentStep,
    stepItems,
    canLeaveCurrentStep,
    shellInstances,
    selectedShellInstanceIds,
    importShellHotkeys,
    shellImporting,
    finishButtonLabel,
    handleFinishWizard,
  }
}
