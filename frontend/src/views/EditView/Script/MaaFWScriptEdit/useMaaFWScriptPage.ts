import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useMaaFWControlConfig } from '@/composables/useMaaFWScriptConfig'
import {
  prepareMaaFWFlavorPage,
  useMaaFWFlavor,
  type MaaFWScriptSlotContext,
} from '@/composables/useMaaFWFlavor'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig, ScriptType } from '@/types/script'
import { useMaaFWScriptDraft } from './useMaaFWScriptDraft'
import { useMaaFWPeriodTasks } from './useMaaFWPeriodTasks'
import { useMaaFWProgressChannel } from './useMaaFWProgressChannel'
import { useMaaFWEnvPrepare } from './useMaaFWEnvPrepare'
import { useMaaFWSetupWizard } from './useMaaFWSetupWizard'
import { useMaaFWProjectIdentity } from './useMaaFWProjectIdentity'
import { useMaaFWEmbeddedImport } from './useMaaFWEmbeddedImport'
import { useMaaFWUpdatePanel } from './useMaaFWUpdatePanel'
import { useMaaFWGamePackage } from './useMaaFWGamePackage'
import { useMaaFWPageHostContext } from '../../MaaFWFlavor/pageHostContext'

export interface MaaFWScriptPageOptions {
  scriptId: string
}

/**
 * MFW 脚本页的编排层：把草稿、控制方式、周期任务、运行环境、内嵌副本、项目更新、
 * 包名推断与引导拼在一起，负责页面加载顺序与卸载收尾，返回模板要用的全部状态与动作。
 *
 * 加载顺序（onMounted）：脚本详情（页面宿主读过就直接用）与模拟器选项并行 → 铺配置与类型 → 设备列表 → 内嵌状态 →
 * 读 interface（期间的控制器 / 资源同步与项目名同步因 `isInitializing` 仍为 true 而只改草稿）
 * → 再读一次内嵌状态 → finally 放开 `isInitializing` → 最后才项目名同步、CDK 预填、包名推断。
 */
export function useMaaFWScriptPage({ scriptId }: MaaFWScriptPageOptions) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MaaFW 脚本编辑')
  const router = useRouter()
  const { getScript, previewMaaFWInterface } = useScriptApi()

  const {
    pageLoading,
    isInitializing,
    enqueue,
    previewLoading,
    previewData,
    maafwConfig,
    formData,
    rules,
    handleChange,
    applyScriptConfig: applyDraftConfig,
  } = useMaaFWScriptDraft(scriptId)

  // flavor 文案以脚本当前类型为准，不看路由 meta：/edit/maafw 与 /edit/m9a 都进这个组件，
  // 而导入完成后后端会按项目内容原地换类型（M9A 项目 → M9A，其它 → MaaFW，uid 不变）。
  // 在页面宿主里时类型是宿主的那一份：写回去宿主才知道要不要换页面。
  const host = useMaaFWPageHostContext()
  const scriptType = host?.scriptType ?? ref<ScriptType>('MaaFW')
  const flavor = useMaaFWFlavor(scriptType)
  const refreshScriptType = async () => {
    try {
      const detail = await getScript(scriptId)
      if (detail?.type) {
        const typeChanged = detail.type !== scriptType.value
        scriptType.value = detail.type
        formData.type = detail.type
        // 换成了另一个特调：把它在脚本页的替换分节与插入点备好（不等，不挡后续流程）
        if (typeChanged) void prepareMaaFWFlavorPage(flavor.value, 'scriptPage')
      }
    } catch (error) {
      logger.warn(`刷新脚本类型失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const control = useMaaFWControlConfig(maafwConfig, previewData, previewLoading, handleChange)
  const { syncControllerResourceSelection, loadEmulatorOptions, loadEmulatorDeviceOptions } =
    control

  const periodTasks = useMaaFWPeriodTasks(maafwConfig, previewData, handleChange)
  const { prunePeriodTaskSelections, syncPeriodTasksFromConfig } = periodTasks

  /** 铺后端配置的唯一入口：先铺草稿，紧接着把周期任务的三个本地列表跟上（两步不能拆开调） */
  const applyScriptConfig = (config: Partial<MaaFWScriptConfig> | null | undefined) => {
    applyDraftConfig(config)
    syncPeriodTasksFromConfig()
  }

  const channel = useMaaFWProgressChannel(scriptId)
  const env = useMaaFWEnvPrepare(scriptId, maafwConfig, channel)
  const { envPreparedPath, runAgentEnvPrepare } = env

  // 页面已卸载：还在跑的异步流程（外壳配置导入）结束时不再跳转
  let pageUnmounted = false
  onBeforeUnmount(() => {
    pageUnmounted = true
  })

  const wizard = useMaaFWSetupWizard({
    scriptId,
    previewData,
    maafwConfig,
    handleChange,
    envReady: env.envReady,
    enqueue,
    flavor,
    host,
    isPageUnmounted: () => pageUnmounted,
  })

  const identity = useMaaFWProjectIdentity({
    maafwConfig,
    formData,
    previewData,
    isInitializing,
    handleChange,
    flavor,
    isWizard: wizard.isWizard,
  })
  const { syncProjectName } = identity

  // 特调插入点的上下文：独有区块可以直接改 maafwConfig 草稿，落盘走 change 事件回到 handleChange
  const flavorSlotContext = computed<MaaFWScriptSlotContext>(() => ({
    scriptId,
    maafwConfig,
    previewData: previewData.value,
    interfaceDisabled: control.interfaceDependentDisabled.value,
    loading: pageLoading.value,
    isWizard: wizard.isWizard.value,
  }))

  const interfaceStats = computed(() => [
    { label: t('edit.task'), value: previewData.value?.tasks.length ?? 0 },
    { label: t('edit.preset'), value: previewData.value?.presets.length ?? 0 },
    { label: t('edit.controller'), value: previewData.value?.controllers.length ?? 0 },
    { label: t('edit.resource'), value: previewData.value?.resources.length ?? 0 },
    { label: t('edit.import2'), value: previewData.value?.importCount ?? 0 },
    { label: 'Agent', value: previewData.value?.agentCount ?? 0 },
  ])

  const runPreview = async (options: { forceEnv?: boolean } = {}) => {
    const path = maafwConfig.Info.Path.trim()
    if (!path) {
      previewData.value = null
      return
    }
    previewLoading.value = true
    try {
      // 带 scriptId：内嵌脚本读的是 AUTO-MAS 的副本，path 只在没有脚本时兜底。
      const response = await previewMaaFWInterface(path, scriptId)
      if (!response || response.code !== 200 || !response.data) {
        previewData.value = null
        message.error(response?.message || 'MaaFW interface 预览失败，请检查后端服务与项目目录')
        return
      }
      previewData.value = response.data as MaaFWInterfacePreviewData
      await syncControllerResourceSelection(true)
      await prunePeriodTaskSelections()
      await syncProjectName()
      // 读到 interface 就把运行环境备好。四个调用方（读取按钮 / 选目录 /
      // 路径变更 / 页面加载）都会经过这里，放在 runPreview 里才不会漏。
      void runAgentEnvPrepare(path, options.forceEnv === true)
    } catch (error) {
      previewData.value = null
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      previewLoading.value = false
    }
  }

  // 「准备运行环境」按钮（失败时即「重试」）：interface 再读一遍，运行环境不吃指纹缓存、
  // 真的重新准备一次——用户点它就是因为环境实际不好使，而指纹只看项目文件动没动，看不出
  // venv 内部坏了。进度与结论都在右侧面板里，不再弹「已读取 xxx」的 toast。
  const handlePreviewInterface = async () => {
    envPreparedPath.value = ''
    await runPreview({ forceEnv: true })
  }

  // 有效根换了（换来源、重新导入）：Info.Path 文本可能没变，但后端按
  // scriptId 解析到的目录已经不是同一个，运行环境要在新根上重新准备一次。这里只
  // 清掉页面内「这个路径备好过」的记忆；后端仍按项目指纹去重，不会真的重装。
  const runPreviewOnNewRoot = async () => {
    envPreparedPath.value = ''
    await runPreview()
  }

  const embedded = useMaaFWEmbeddedImport({
    scriptId,
    maafwConfig,
    formData,
    channel,
    refreshScriptType,
    runPreviewOnNewRoot,
    isPageUnmounted: () => pageUnmounted,
  })
  const { refreshEmbeddedStatus } = embedded

  const update = useMaaFWUpdatePanel({
    scriptId,
    maafwConfig,
    previewData,
    handleChange,
    runPreview: () => runPreview(),
  })
  const { prefillMirrorChyanCdk } = update

  const { syncGamePackageName, handleResourceChangeWithPackage } = useMaaFWGamePackage({
    scriptId,
    maafwConfig,
    handleChange,
    resolveResourceName: control.resolveResourceName,
    handleResourceChange: control.handleResourceChange,
  })

  const handleCancel = () => {
    router.push('/scripts')
  }

  const load = async () => {
    pageLoading.value = true
    let scriptLoaded = false
    try {
      // 页面宿主已经读过脚本详情就直接用（null 是读过但没读到），不再请求一次
      const initialScript = host?.takeInitialScript()
      const [scriptDetail] = await Promise.all([
        initialScript !== undefined ? initialScript : getScript(scriptId),
        loadEmulatorOptions(),
      ])
      if (!scriptDetail) {
        message.error(t('edit.scriptDoesNotExist'))
        router.push('/scripts')
        return
      }
      applyScriptConfig(scriptDetail.config as Partial<MaaFWScriptConfig>)
      scriptType.value = scriptDetail.type
      formData.type = scriptDetail.type
      // 特调在脚本页的替换分节与插入点：与后面的加载并行备好，不等它，不改动请求顺序
      void prepareMaaFWFlavorPage(flavor.value, 'scriptPage')
      scriptLoaded = true
      if (!maafwConfig.Info.Name) {
        maafwConfig.Info.Name = scriptDetail.name ?? '新 MFW 脚本'
        formData.name = maafwConfig.Info.Name
      }

      if (maafwConfig.Emulator.Id && maafwConfig.Emulator.Id !== '-') {
        await loadEmulatorDeviceOptions(maafwConfig.Emulator.Id)
      }
      await refreshEmbeddedStatus()
      if (maafwConfig.Info.Path) {
        await runPreview()
        // 老脚本第一次打开：预览会让后端顺手完成导入，面板要按导入后的状态重画。
        await refreshEmbeddedStatus()
      }
    } catch (error) {
      logger.error(`加载脚本失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error(t('edit.couldNotLoadScript'))
      router.push('/scripts')
    } finally {
      pageLoading.value = false
      isInitializing.value = false
    }
    // 放在 isInitializing 复位之后：handleChange 在初始化期间不落盘，
    // 预填要真正写进脚本配置而不是只改本地草稿。
    if (scriptLoaded) {
      await syncProjectName()
      await prefillMirrorChyanCdk()
      await syncGamePackageName(false)
    }
  }

  onMounted(load)

  return {
    pageLoading,
    previewLoading,
    previewData,
    maafwConfig,
    formData,
    rules,
    handleChange,
    applyScriptConfig,
    scriptType,
    flavor,
    refreshScriptType,
    ...control,
    handleResourceChangeWithPackage,
    ...periodTasks,
    ...env,
    ...embedded,
    ...update,
    ...wizard,
    ...identity,
    flavorSlotContext,
    interfaceStats,
    handlePreviewInterface,
    handleCancel,
    load,
  }
}
