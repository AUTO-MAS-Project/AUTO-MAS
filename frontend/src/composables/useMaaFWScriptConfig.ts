import { computed, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ComboBoxItem } from '@/api'
import { useMaaFWApi } from '@/composables/useMaaFWApi'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
import {
  WS_MAAFW_ENV_PREPARE_PROGRESS,
  WS_MAAFW_PROJECT_UPDATE_PROGRESS,
  type WSMaaFWEnvPrepareProgressData,
  type WSMaaFWProjectUpdateProgressData,
} from '@/services/websocket/types'
import type {
  MaaFWAgentEnvPrepareData,
  MaaFWControllerInfo,
  MaaFWInterfacePreviewData,
  MaaFWScriptConfig,
  Script,
  ScriptType,
} from '@/types/script'

const logger = window.electronAPI.getLogger('MaaFW脚本编辑')

export type EmulatorType = 'general' | 'mumu' | 'ldplayer'

const EMULATOR_TYPE_LABELS: Record<EmulatorType, string> = {
  general: '通用模拟器',
  mumu: 'MuMu 模拟器',
  ldplayer: '雷电模拟器',
}

type MaaFWProjectUpdateSource = MaaFWScriptConfig['Update']['Source']
type MaaFWExplicitUpdateSource = Exclude<MaaFWProjectUpdateSource, ''>
type MaaFWConcreteUpdateChannel = Exclude<MaaFWScriptConfig['Update']['Channel'], ''>

const DEFAULT_MAAFW_UPDATE_SOURCE: MaaFWExplicitUpdateSource = 'MirrorChyan'
const MAAFW_UPDATE_SOURCES: MaaFWExplicitUpdateSource[] = ['MirrorChyan', 'GitHub']
const MAAFW_UPDATE_CHANNELS: MaaFWConcreteUpdateChannel[] = ['stable', 'beta']
const MAAFW_DIRECT_CONTROLLER_TYPES = ['Adb', 'Win32'] as const

export type MaaFWProjectUpdateStatus = 'idle' | 'running' | 'completed' | 'failed'
export type MaaFWProjectUpdateAction = 'check' | 'apply'
export type MaaFWAgentEnvProgressStatus = 'idle' | 'running' | 'completed' | 'failed'

type MaaFWPendingSave = {
  revision: number
  category: keyof MaaFWScriptConfig
  key: string
  value: unknown
}

const PROJECT_UPDATE_STAGE_LABELS: Record<string, string> = {
  checking: '正在检查可用版本',
  downloading: '正在下载项目资源',
  validating: '正在校验下载内容',
  extracting: '正在解压项目资源',
  switching: '正在切换项目版本',
  preparing_environment: '正在准备运行环境',
  completed: '项目更新已完成',
  failed: '项目更新失败',
}

const PROJECT_UPDATE_STAGE_PROGRESS: Record<string, number> = {
  checking: 5,
  validating: 75,
  extracting: 82,
  switching: 90,
  preparing_environment: 95,
  completed: 100,
}

const AGENT_ENV_STAGE_LABELS: Record<string, string> = {
  checking: '正在检查运行环境',
  resolving: '正在解析 Agent 运行要求',
  preparing_runtime: '正在准备 Runner 运行环境',
  creating_venv: '正在创建隔离 Python 环境',
  installing_dependencies: '正在安装 Agent 依赖',
  preparing_agents: '正在准备项目 Agent',
  completed: '运行环境准备完成',
  failed: '运行环境准备失败',
}

type MaaFWDirectControllerType = (typeof MAAFW_DIRECT_CONTROLLER_TYPES)[number]

export const isDirectControllerType = (
  controllerType?: string | null
): controllerType is MaaFWDirectControllerType =>
  MAAFW_DIRECT_CONTROLLER_TYPES.includes(controllerType as MaaFWDirectControllerType)

export const getAgentRuntimeLabel = (runtimeKind?: string | null) => {
  if (runtimeKind === 'embedded') return '主进程内嵌'
  if (runtimeKind === 'project_python') return '项目自带 Python'
  if (runtimeKind === 'project_binary') return '项目自带程序'
  if (runtimeKind === 'isolated_venv') return '隔离 venv'
  if (runtimeKind === 'external') return '外部环境'
  return runtimeKind || '未知环境'
}

export const getAgentRuntimeColor = (runtimeKind?: string | null) => {
  if (runtimeKind === 'embedded') return 'purple'
  if (runtimeKind === 'project_python') return 'green'
  if (runtimeKind === 'project_binary') return 'cyan'
  if (runtimeKind === 'isolated_venv') return 'blue'
  if (runtimeKind === 'external') return 'orange'
  return 'default'
}

const isMaaFWUpdateSource = (value: string): value is MaaFWExplicitUpdateSource =>
  MAAFW_UPDATE_SOURCES.includes(value as MaaFWExplicitUpdateSource)

const isMaaFWUpdateChannel = (value: string): value is MaaFWConcreteUpdateChannel =>
  MAAFW_UPDATE_CHANNELS.includes(value as MaaFWConcreteUpdateChannel)

const updateSourceOptions = [
  { label: 'MirrorChyan', value: 'MirrorChyan' },
  { label: 'GitHub', value: 'GitHub' },
] satisfies Array<{ label: string; value: MaaFWExplicitUpdateSource }>

const updateChannelOptions = [
  { label: '稳定版', value: 'stable' as MaaFWConcreteUpdateChannel },
  { label: '测试版', value: 'beta' as MaaFWConcreteUpdateChannel },
]

const getDefaultMaaFWScriptConfig = (): MaaFWScriptConfig => ({
  Info: {
    Name: '',
    ProjectLabel: '',
    Path: '',
    Controller: '',
    Resource: '',
  },
  Emulator: {
    Id: '-',
    Index: '-',
  },
  Device: {
    AdbPath: '',
    AdbAddress: '',
    AdbScreencapMethods: -57,
    AdbInputMethods: -1,
    HWnd: 0,
    Win32ScreencapMethod: 0,
    Win32MouseMethod: 0,
    Win32KeyboardMethod: 0,
    GamepadType: 0,
    PlayCoverAddress: '',
    PlayCoverUuid: '',
  },
  Game: {
    Path: '',
    Arguments: '',
    WaitTime: 60,
    CloseOnFinish: true,
  },
  Update: {
    IfAutoUpdate: true,
    Source: DEFAULT_MAAFW_UPDATE_SOURCE,
    Channel: 'stable',
    MirrorChyanCDK: '',
    GitHubRepo: '',
    GitHubTag: '',
    GitHubAssetPattern: '',
  },
  Run: {
    ProxyTimesLimit: 0,
    RunTimesLimit: 1,
    RunTimeLimit: 30,
    DailyOnceTasks: '[ ]',
    WeeklyOnceTasks: '[ ]',
    MonthlyOnceTasks: '[ ]',
  },
  Managed: {},
})

/**
 * MaaFW 脚本配置的共享逻辑 composable。
 * 由 MaaFWScriptEdit.vue（编辑页）和 MaaFWSetupWizard.vue（引导页）共同使用。
 *
 * 注意：
 * - 本 composable 不处理路由跳转（router.push），由各页面自行处理。
 * - loadScript 不会设置 isSetupMode，由各页面在调用后根据 maafwConfig.Info.Path 自行决定。
 */
export function useMaaFWScriptConfig(scriptId: string) {
  const registryApi = useScriptRegistryApi()
  const { getSettings } = useSettingsApi()
  const { loading: interfaceLoading, previewInterface } = useMaaFWApi()
  const { loading: agentEnvLoading, prepareAgentEnv } = useMaaFWApi()
  const { loading: projectUpdateLoading, updateProjectResources } = useMaaFWApi()

  const pageLoading = ref(false)
  const isInitializing = ref(true)
  const isSaving = ref(false)
  const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const saveErrorMessage = ref('')
  const hasUnsavedChanges = ref(false)
  const previewData = ref<MaaFWInterfacePreviewData | null>(null)
  const agentEnvResult = ref<MaaFWAgentEnvPrepareData | null>(null)
  const agentEnvProgressStatus = ref<MaaFWAgentEnvProgressStatus>('idle')
  const agentEnvProgressStage = ref('')
  const agentEnvProgressPercent = ref<number | null>(null)
  const agentEnvProgressMessage = ref('')
  const agentEnvProgressLogs = ref<string[]>([])
  const agentEnvProgressDownloadedBytes = ref<number | null>(null)
  const agentEnvProgressTotalBytes = ref<number | null>(null)
  const projectUpdateLogs = ref<string[]>([])
  const projectUpdateStatus = ref<MaaFWProjectUpdateStatus>('idle')
  const projectUpdateAction = ref<MaaFWProjectUpdateAction>('check')
  const projectUpdateStage = ref('')
  const projectUpdateProgress = ref<number | null>(null)
  const projectUpdateDownloadPercent = ref<number | null>(null)
  const projectUpdateDownloadedBytes = ref<number | null>(null)
  const projectUpdateTotalBytes = ref<number | null>(null)
  const projectUpdateMessage = ref('')
  const projectUpdateProviderErrorCode = ref<number | null>(null)
  const projectUpdateDiscoveredVersion = ref('')
  const projectUpdateMetadataSource = ref('')
  const projectUpdatePackageSource = ref('')
  const scriptEditHint = ref<Script['editHint']>(null)
  const scriptIconUrl = ref<string | null>(null)
  const dailyOnceTasks = ref<string[]>([])
  const weeklyOnceTasks = ref<string[]>([])
  const monthlyOnceTasks = ref<string[]>([])
  const globalUpdateSource = ref<string>('')
  const globalUpdateChannel = ref<string>('')
  const globalMirrorChyanCDK = ref<string>('')
  const pendingSaves: MaaFWPendingSave[] = []
  let disposed = false
  let latestSaveRevision = 0
  let persistedSaveRevision = 0
  let saveDrainPromise: Promise<boolean> | null = null
  let lastUpdateErrorMessage = ''
  let saveStatusTimer: ReturnType<typeof setTimeout> | null = null
  let projectUpdateSubscriptionId: string | null = null
  let agentEnvProgressSubscriptionId: string | null = null
  let agentEnvGeneration = 0
  let agentEnvPrepareRequest: {
    path: string
    generation: number
    promise: Promise<void>
  } | null = null

  const emulatorLoading = ref(false)
  const emulatorOptionsReady = ref(false)
  const emulatorDeviceLoading = ref(false)
  const emulatorOptions = ref<ComboBoxItem[]>([])
  const emulatorDeviceOptions = ref<ComboBoxItem[]>([])
  const emulatorTypeById = ref<Record<string, EmulatorType>>({})
  let emulatorOptionsLoaded = false
  let emulatorOptionsPromise: Promise<void> | null = null
  const emulatorDeviceOptionsCache = new Map<string, ComboBoxItem[]>()
  const emulatorDeviceRequests = new Map<string, Promise<ComboBoxItem[] | null>>()

  const maafwConfig = reactive<MaaFWScriptConfig>(getDefaultMaaFWScriptConfig())

  const formData = reactive({
    type: 'MaaFW' as ScriptType,
    get name() {
      return maafwConfig.Info.Name
    },
    set name(value) {
      maafwConfig.Info.Name = value
    },
    get path() {
      return maafwConfig.Info.Path
    },
    set path(value) {
      maafwConfig.Info.Path = value
    },
  })

  const rules = {
    name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
    path: [{ required: true, message: '请选择 MaaFramework 项目目录', trigger: 'blur' }],
  }

  const isAutoUpdateDisabled = computed(() =>
    Boolean(previewData.value && !previewData.value.project.version)
  )

  const isInterfaceReady = computed(() => Boolean(previewData.value))
  const isAgentEnvReady = computed(
    () => Boolean(agentEnvResult.value) && agentEnvResult.value?.status !== 'error'
  )
  const isAgentEnvFailed = computed(() => agentEnvResult.value?.status === 'error')
  const isAgentEnvPreparing = computed(
    () => agentEnvProgressStatus.value === 'running' || agentEnvLoading.value
  )

  const hasEffectiveMirrorChyanCDK = computed(
    () =>
      Boolean(String(maafwConfig.Update.MirrorChyanCDK || '').trim()) ||
      Boolean(String(globalMirrorChyanCDK.value || '').trim())
  )
  const projectUpdateMirrorSourceBlocked = computed(
    () => !hasEffectiveMirrorChyanCDK.value && maafwConfig.Update.Source === 'MirrorChyan'
  )
  const isProjectUpdateRunning = computed(
    () => projectUpdateStatus.value === 'running' || projectUpdateLoading.value
  )

  const projectUpdateDisabled = computed(
    () =>
      !maafwConfig.Info.Path ||
      !previewData.value ||
      isAutoUpdateDisabled.value ||
      isSaving.value ||
      hasUnsavedChanges.value ||
      interfaceLoading.value ||
      isAgentEnvPreparing.value ||
      isProjectUpdateRunning.value
  )

  const periodTaskOptions = computed(() =>
    (previewData.value?.tasks || []).map(task => ({
      label: task.label ? `${task.label}（${task.name}）` : task.name,
      value: task.name,
    }))
  )

  const previewProjectTitle = computed(() => {
    if (!previewData.value) return '-'
    const project = previewData.value.project
    return project.title || project.label || project.name
  })

  const interfaceStats = computed(() => [
    { label: '任务', value: previewData.value?.tasks.length ?? 0 },
    { label: '预设', value: previewData.value?.presets.length ?? 0 },
    { label: '控制器', value: previewData.value?.controllers.length ?? 0 },
    { label: '资源', value: previewData.value?.resources.length ?? 0 },
    { label: '导入', value: previewData.value?.importCount ?? 0 },
    { label: 'Agent', value: previewData.value?.agentCount ?? 0 },
  ])

  const setSaveStatus = (status: 'idle' | 'saving' | 'saved' | 'error', errorMessage = '') => {
    if (disposed) return
    if (saveStatusTimer) {
      clearTimeout(saveStatusTimer)
      saveStatusTimer = null
    }
    saveStatus.value = status
    saveErrorMessage.value = errorMessage
    if (status === 'saved') {
      saveStatusTimer = setTimeout(() => {
        if (disposed) return
        saveStatus.value = 'idle'
        saveStatusTimer = null
      }, 2000)
    }
  }

  const copyToClipboard = async (text: string) => {
    const value = String(text || '')
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      message.success('已复制')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`复制失败: ${errorMsg}`)
      message.error('复制失败')
    }
  }

  const normalizeProjectScriptName = (rawName?: string | null) => {
    if (!rawName) return ''

    const primaryName = rawName
      .split(/[|｜]/)[0]
      .trim()
      .replace(/\s+(?:版本号\s*[:：]?\s*)?v?\d+(?:\.\d+)+(?:[-+][\w.]+)?$/i, '')
      .trim()

    return primaryName || rawName.trim()
  }

  const resolveProjectScriptName = (data: MaaFWInterfacePreviewData) => {
    const project = data.project
    return (
      normalizeProjectScriptName(project.title) ||
      normalizeProjectScriptName(project.label) ||
      normalizeProjectScriptName(project.name)
    )
  }

  const resolveProjectLabel = (data: MaaFWInterfacePreviewData) => {
    return resolveProjectScriptName(data)
  }

  const resolveUpdateSource = (value?: string | null): MaaFWProjectUpdateSource => {
    const source = value ?? ''
    if (isMaaFWUpdateSource(source)) return source
    if (isMaaFWUpdateSource(globalUpdateSource.value)) {
      return globalUpdateSource.value
    }
    // The host updater also supports sources that MaaFW cannot consume.
    // Keep the MaaFW fallback deterministic while preserving the persisted
    // blank value as "inherit" on the backend.
    return DEFAULT_MAAFW_UPDATE_SOURCE
  }

  const resolveUpdateChannel = (value?: string | null): MaaFWConcreteUpdateChannel => {
    if (value && isMaaFWUpdateChannel(value)) return value
    if (globalUpdateChannel.value && isMaaFWUpdateChannel(globalUpdateChannel.value)) {
      return globalUpdateChannel.value
    }
    return MAAFW_UPDATE_CHANNELS[0]
  }

  const normalizeUpdateConfig = (
    update: MaaFWScriptConfig['Update']
  ): MaaFWScriptConfig['Update'] => ({
    ...update,
    Source: resolveUpdateSource(update.Source),
    Channel: resolveUpdateChannel(update.Channel),
  })

  const normalizeScriptConfig = (config: Partial<MaaFWScriptConfig> | null | undefined) => {
    const defaults = getDefaultMaaFWScriptConfig()
    return {
      Info: { ...defaults.Info, ...config?.Info },
      Emulator: { ...defaults.Emulator, ...config?.Emulator },
      Device: { ...defaults.Device, ...config?.Device },
      Game: { ...defaults.Game, ...config?.Game },
      Update: normalizeUpdateConfig({ ...defaults.Update, ...config?.Update }),
      Run: { ...defaults.Run, ...config?.Run },
      Managed: { ...defaults.Managed, ...config?.Managed },
    }
  }

  const parseTaskNameList = (raw: string | string[] | null | undefined): string[] => {
    if (Array.isArray(raw)) {
      return Array.from(new Set(raw.map(String).filter(Boolean)))
    }
    if (typeof raw === 'string' && raw.trim()) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          return Array.from(new Set(parsed.map(String).filter(Boolean)))
        }
      } catch {
        return []
      }
    }
    return []
  }

  const stringifyTaskNameList = (value: string[]): string => JSON.stringify(value)

  const applyScriptConfig = (config: Partial<MaaFWScriptConfig> | null | undefined) => {
    const normalized = normalizeScriptConfig(config)
    Object.assign(maafwConfig.Info, normalized.Info)
    Object.assign(maafwConfig.Emulator, normalized.Emulator)
    Object.assign(maafwConfig.Device, normalized.Device)
    Object.assign(maafwConfig.Game, normalized.Game)
    Object.assign(maafwConfig.Update, normalized.Update)
    Object.assign(maafwConfig.Run, normalized.Run)
    maafwConfig.Managed = { ...normalized.Managed }
    dailyOnceTasks.value = parseTaskNameList(normalized.Run.DailyOnceTasks)
    weeklyOnceTasks.value = parseTaskNameList(normalized.Run.WeeklyOnceTasks)
    monthlyOnceTasks.value = parseTaskNameList(normalized.Run.MonthlyOnceTasks)
    maafwConfig.Run.DailyOnceTasks = stringifyTaskNameList(dailyOnceTasks.value)
    maafwConfig.Run.WeeklyOnceTasks = stringifyTaskNameList(weeklyOnceTasks.value)
    maafwConfig.Run.MonthlyOnceTasks = stringifyTaskNameList(monthlyOnceTasks.value)
  }

  const updateScriptConfig = async (config: Record<string, unknown>) => {
    lastUpdateErrorMessage = ''
    try {
      await registryApi.updateScript(scriptId, config)
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      lastUpdateErrorMessage = errorMsg
      if (!disposed) message.error(errorMsg)
      return false
    }
  }

  const buildPendingSavePatch = (entries: MaaFWPendingSave[]): Record<string, unknown> => {
    const patch: Record<string, Record<string, unknown>> = {}
    entries.forEach(entry => {
      const categoryPatch = patch[entry.category] ?? {}
      categoryPatch[entry.key] = entry.value
      patch[entry.category] = categoryPatch
    })
    return patch
  }

  const drainPendingSaves = async (): Promise<boolean> => {
    isSaving.value = true
    setSaveStatus('saving')
    let activeBatch: MaaFWPendingSave[] = []
    try {
      while (pendingSaves.length > 0) {
        activeBatch = pendingSaves.splice(0, pendingSaves.length)
        const latestBatchRevision = Math.max(...activeBatch.map(entry => entry.revision))
        const success = await updateScriptConfig(buildPendingSavePatch(activeBatch))
        if (!success) {
          pendingSaves.unshift(...activeBatch)
          activeBatch = []
          if (!disposed) {
            hasUnsavedChanges.value = true
            setSaveStatus(
              'error',
              lastUpdateErrorMessage ? `保存失败：${lastUpdateErrorMessage}` : '保存失败，请重试'
            )
          }
          return false
        }

        persistedSaveRevision = Math.max(persistedSaveRevision, latestBatchRevision)
        logger.info(
          `配置已保存: ${activeBatch.map(entry => `${entry.category}.${entry.key}`).join(', ')}`
        )
        activeBatch = []
      }

      const fullyPersisted = persistedSaveRevision >= latestSaveRevision
      if (!disposed) {
        hasUnsavedChanges.value = !fullyPersisted
        if (fullyPersisted) setSaveStatus('saved')
      }
      return fullyPersisted
    } catch (error) {
      if (activeBatch.length > 0) pendingSaves.unshift(...activeBatch)
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
      if (!disposed) {
        hasUnsavedChanges.value = true
        setSaveStatus('error', `保存失败：${errorMsg}`)
      }
      return false
    } finally {
      if (!disposed) isSaving.value = false
      saveDrainPromise = null
    }
  }

  const ensureSaveDrain = () => {
    if (!saveDrainPromise) saveDrainPromise = drainPendingSaves()
    return saveDrainPromise
  }

  const handleChange = async (
    category: keyof MaaFWScriptConfig,
    key: string,
    value: unknown,
    force = false
  ) => {
    if (disposed) return false
    if (!force && isInitializing.value) return true

    if (category === 'Update' || (category === 'Info' && key === 'Path')) {
      projectUpdateAction.value = 'check'
    }

    const revision = ++latestSaveRevision
    pendingSaves.push({ revision, category, key, value })
    hasUnsavedChanges.value = true
    return await ensureSaveDrain()
  }

  const handlePeriodTaskChange = async (
    key: 'DailyOnceTasks' | 'WeeklyOnceTasks' | 'MonthlyOnceTasks',
    values: string[]
  ) => {
    const normalized = Array.from(new Set(values.filter(Boolean)))
    if (key === 'DailyOnceTasks') {
      dailyOnceTasks.value = normalized
    } else if (key === 'WeeklyOnceTasks') {
      weeklyOnceTasks.value = normalized
    } else {
      monthlyOnceTasks.value = normalized
    }

    maafwConfig.Run[key] = stringifyTaskNameList(normalized)
    await handleChange('Run', key, maafwConfig.Run[key])
  }

  const prunePeriodTaskSelections = async () => {
    if (!previewData.value) return

    const availableTasks = new Set(previewData.value.tasks.map(task => task.name))
    const nextDailyTasks = dailyOnceTasks.value.filter(taskName => availableTasks.has(taskName))
    const nextWeeklyTasks = weeklyOnceTasks.value.filter(taskName => availableTasks.has(taskName))
    const nextMonthlyTasks = monthlyOnceTasks.value.filter(taskName => availableTasks.has(taskName))
    const dailyChanged = nextDailyTasks.length !== dailyOnceTasks.value.length
    const weeklyChanged = nextWeeklyTasks.length !== weeklyOnceTasks.value.length
    const monthlyChanged = nextMonthlyTasks.length !== monthlyOnceTasks.value.length

    if (dailyChanged) {
      await handlePeriodTaskChange('DailyOnceTasks', nextDailyTasks)
    }
    if (weeklyChanged) {
      await handlePeriodTaskChange('WeeklyOnceTasks', nextWeeklyTasks)
    }
    if (monthlyChanged) {
      await handlePeriodTaskChange('MonthlyOnceTasks', nextMonthlyTasks)
    }
  }

  // ---- Controller / Resource helpers ----

  const controllerOptions = computed(() => previewData.value?.controllers || [])
  const directControllerOptions = computed(() =>
    controllerOptions.value.filter(controller => isDirectControllerType(controller.type))
  )
  const unsupportedControllerOptions = computed(() =>
    controllerOptions.value.filter(controller => !isDirectControllerType(controller.type))
  )
  const unsupportedControllerMessage = computed(() => {
    const names = unsupportedControllerOptions.value
      .map(controller => `${controller.label || controller.name}(${controller.type})`)
      .join('、')
    return `AUTO-MAS MaaFW Direct 只联动 ADB / Win32；${names} 建议使用项目原 UI。`
  })

  const getDefaultControllerName = () => {
    const wantsAdb = maafwConfig.Emulator.Id && maafwConfig.Emulator.Id !== '-'
    if (wantsAdb) {
      const adbController = directControllerOptions.value.find(c => c.type === 'Adb')
      if (adbController) return adbController.name
    }
    return directControllerOptions.value[0]?.name || ''
  }

  const resolveControllerName = (controllerName?: string) => {
    if (controllerName && directControllerOptions.value.some(c => c.name === controllerName)) {
      return controllerName
    }
    return getDefaultControllerName()
  }

  const effectiveControllerName = computed(() => resolveControllerName(maafwConfig.Info.Controller))
  const effectiveController = computed(
    () => controllerOptions.value.find(item => item.name === effectiveControllerName.value) || null
  )
  const effectiveControllerType = computed(() => effectiveController.value?.type || '')
  const isAdbController = computed(() => effectiveControllerType.value === 'Adb')
  const isDesktopController = computed(() => effectiveControllerType.value === 'Win32')

  const getResourceOptionsByController = (controllerName: string) => {
    const resources = previewData.value?.resources || []
    if (!controllerName) return resources
    return resources.filter(r => r.controller.length === 0 || r.controller.includes(controllerName))
  }

  const resourceOptions = computed(() =>
    getResourceOptionsByController(effectiveControllerName.value)
  )

  const resolveResourceName = (
    resourceName?: string,
    controllerName = effectiveControllerName.value
  ) => {
    const resources = getResourceOptionsByController(controllerName)
    if (resourceName && resources.some(r => r.name === resourceName)) {
      return resourceName
    }
    return resources[0]?.name || ''
  }

  const interfaceDependentDisabled = computed(() => interfaceLoading.value || !previewData.value)

  const handleControllerChange = async () => {
    maafwConfig.Info.Resource = ''
    const nextController = resolveControllerName(maafwConfig.Info.Controller)
    const nextResource = resolveResourceName('', nextController)
    maafwConfig.Info.Controller = nextController
    maafwConfig.Info.Resource = nextResource
    await handleChange('Info', 'Controller', maafwConfig.Info.Controller)
    await handleChange('Info', 'Resource', maafwConfig.Info.Resource)
  }

  const handleResourceChange = async () => {
    maafwConfig.Info.Resource = resolveResourceName(maafwConfig.Info.Resource)
    await handleChange('Info', 'Resource', maafwConfig.Info.Resource)
  }

  const syncControllerResourceSelection = (persist = false) => {
    if (!previewData.value) return
    const nextController = resolveControllerName(maafwConfig.Info.Controller)
    const nextResource = resolveResourceName(maafwConfig.Info.Resource, nextController)
    const controllerChanged = maafwConfig.Info.Controller !== nextController
    const resourceChanged = maafwConfig.Info.Resource !== nextResource
    maafwConfig.Info.Controller = nextController
    maafwConfig.Info.Resource = nextResource
    if (persist && (controllerChanged || resourceChanged)) {
      handleChange('Info', 'Controller', nextController)
      handleChange('Info', 'Resource', nextResource)
    }
  }

  // ---- Emulator helpers ----

  const selectedEmulatorType = computed(() => emulatorTypeById.value[maafwConfig.Emulator.Id])

  const selectedEmulatorLabel = computed(() => {
    if (!maafwConfig.Emulator.Id || maafwConfig.Emulator.Id === '-') return '未选择模拟器'
    const emulatorType = selectedEmulatorType.value
    return emulatorType ? EMULATOR_TYPE_LABELS[emulatorType] : '模拟器类型加载中'
  })

  const selectedEmulatorCapability = computed(() => {
    const emulatorType = selectedEmulatorType.value
    if (!emulatorType) return null
    return previewData.value?.controlCapabilities.emulatorExtras[emulatorType] || null
  })

  const adbControlStrategyMessage = computed(() => {
    if (!maafwConfig.Emulator.Id || maafwConfig.Emulator.Id === '-') {
      return '未选择模拟器时，ADB controller 将使用 MaaFW 默认 ADB 控制策略'
    }
    if (!previewData.value) {
      return '读取 interface 后会展示当前 MaaFW 包可用的模拟器增强能力'
    }

    const capability = selectedEmulatorCapability.value
    if (capability?.screencap || capability?.input) {
      return `已根据 ${selectedEmulatorLabel.value} 和当前 MaaFW 包能力启用可用的 EmulatorExtras`
    }
    return `${selectedEmulatorLabel.value} 当前没有可用的 EmulatorExtras 能力，运行时使用 MaaFW 默认 ADB 控制策略`
  })

  const adbControlStrategyItems = computed(() => {
    const capability = selectedEmulatorCapability.value
    const screencapWithExtras = Boolean(capability?.screencap)
    const inputWithExtras = Boolean(capability?.input)

    return [
      {
        label: '模拟器',
        value: selectedEmulatorLabel.value,
      },
      {
        label: '截图',
        value: screencapWithExtras
          ? 'MaaFW 默认截图集合（包含 EmulatorExtras）'
          : 'MaaFW 默认截图集合（不启用 EmulatorExtras）',
      },
      {
        label: '输入',
        value: inputWithExtras
          ? 'MaaFW 全量输入集合（优先 EmulatorExtras）'
          : 'MaaFW 默认输入集合（不启用 EmulatorExtras）',
      },
    ]
  })

  // ---- Agent env computed ----

  const agentEnvAlertType = computed(() => {
    if (agentEnvResult.value?.status === 'error') return 'error'
    if (agentEnvResult.value?.agentCount === 0) return 'info'
    return 'success'
  })

  const agentEnvSummary = computed(() => {
    if (!agentEnvResult.value) return ''
    if (agentEnvResult.value.status === 'error') return 'MaaFW 运行环境准备失败'
    if (agentEnvResult.value.agentCount === 0) return 'MaaFW Runner 环境已准备完成'
    return `MaaFW 运行环境已准备完成，共 ${agentEnvResult.value.agentCount} 个 Agent`
  })

  const agentEnvDescription = computed(() => {
    if (!agentEnvResult.value) return ''
    if (agentEnvResult.value.status === 'error') {
      return agentEnvResult.value.message || '请查看下方准备日志定位失败步骤'
    }
    if (agentEnvResult.value.agentCount === 0) {
      return '当前 MaaFW 项目没有声明 Agent，无需准备 Agent 子进程环境。'
    }
    return 'Runner 隔离 venv 已预热；项目内二进制 Agent 直接使用；项目自带 Python 只做健康检查；缺少项目 Python 时使用项目专属隔离 venv。'
  })

  const agentEnvChecklistDescription = computed(() => {
    if (isAgentEnvFailed.value) {
      return agentEnvResult.value?.message || '准备失败，请查看下方日志后重试'
    }
    if (isAgentEnvReady.value) {
      const agentCount = agentEnvResult.value?.agentCount ?? 0
      return agentCount > 0
        ? `运行环境已就绪，共 ${agentCount} 个 Agent`
        : '运行环境已就绪，当前项目没有声明 Agent'
    }
    return '预热 Runner 隔离环境并安装 Agent 依赖，避免首次运行时长时间卡在环境安装'
  })

  // ---- Sync helpers ----

  const syncScriptNameFromProject = async (data: MaaFWInterfacePreviewData) => {
    const nextName = resolveProjectScriptName(data)
    if (!nextName || nextName === maafwConfig.Info.Name) return

    maafwConfig.Info.Name = nextName
    await handleChange('Info', 'Name', nextName, true)
  }

  const syncProjectLabelFromProject = async (data: MaaFWInterfacePreviewData) => {
    const nextLabel = resolveProjectLabel(data)
    if (!nextLabel || nextLabel === maafwConfig.Info.ProjectLabel) return

    maafwConfig.Info.ProjectLabel = nextLabel
    await handleChange('Info', 'ProjectLabel', nextLabel, true)
  }

  const toProgressNumber = (value: number | null | undefined): number | null => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null
    return value
  }

  const handleProjectUpdateProgress = (data: WSMaaFWProjectUpdateProgressData) => {
    if (data.scriptId && data.scriptId !== scriptId) return

    const stage = String(data.stage || '')
    const phase = String(data.phase || '')
    const status = String(data.status || '').toLowerCase()
    const isFinal = data.final === true
    const terminalEvent = isFinal || stage === 'failed'
    if (
      !terminalEvent &&
      !projectUpdateLoading.value &&
      (projectUpdateStatus.value === 'completed' || projectUpdateStatus.value === 'failed')
    ) {
      return
    }
    const percent = toProgressNumber(data.percent)
    const downloadedBytes = toProgressNumber(data.downloaded_bytes)
    const totalBytes = toProgressNumber(data.total_bytes)

    projectUpdateStage.value =
      phase === 'preparing_environment' && stage !== 'completed' && stage !== 'failed'
        ? `正在准备运行环境${data.message ? ` · ${data.message}` : ''}`
        : PROJECT_UPDATE_STAGE_LABELS[stage] || data.message || stage || '正在更新项目资源'
    projectUpdateMessage.value = data.message || ''
    if (typeof data.provider_error_code === 'number') {
      projectUpdateProviderErrorCode.value = data.provider_error_code
    }
    if (data.version) projectUpdateDiscoveredVersion.value = data.version
    if (data.metadata_source) projectUpdateMetadataSource.value = data.metadata_source
    if (data.package_source) projectUpdatePackageSource.value = data.package_source
    if (status === 'version_discovered' && data.version) {
      projectUpdateStage.value = `已发现版本 ${data.version}`
    }
    if (phase === 'preparing_environment' && stage !== 'completed' && stage !== 'failed') {
      projectUpdateProgress.value = 95
    } else if (stage === 'preparing_environment') {
      projectUpdateProgress.value = percent === null ? 95 : Math.min(Math.max(percent, 0), 100)
    } else if (stage === 'downloading') {
      projectUpdateDownloadPercent.value =
        percent === null ? null : Math.min(Math.max(percent, 0), 100)
      projectUpdateProgress.value =
        projectUpdateDownloadPercent.value === null
          ? null
          : 10 + projectUpdateDownloadPercent.value * 0.6
    } else if (stage === 'completed' && !isFinal) {
      projectUpdateProgress.value = Math.min(Math.max(projectUpdateProgress.value ?? 90, 90), 95)
    } else if (stage in PROJECT_UPDATE_STAGE_PROGRESS) {
      projectUpdateProgress.value = PROJECT_UPDATE_STAGE_PROGRESS[stage]
    } else if (percent !== null) {
      projectUpdateProgress.value = Math.min(Math.max(percent, 0), 100)
    }
    if (downloadedBytes !== null) projectUpdateDownloadedBytes.value = downloadedBytes
    if (totalBytes !== null) projectUpdateTotalBytes.value = totalBytes

    if (stage === 'failed' || status === 'failed' || status === 'error') {
      projectUpdateStatus.value = 'failed'
      return
    }
    if (isFinal) {
      projectUpdateStatus.value = 'completed'
      projectUpdateProgress.value = 100
      return
    }
    projectUpdateStatus.value = 'running'
  }

  const normalizeProgressPath = (value: string) =>
    value.replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase()

  const handleAgentEnvProgress = (data: WSMaaFWEnvPrepareProgressData) => {
    if (disposed) return
    if (data.scriptId && data.scriptId !== scriptId) return
    if (
      data.project_path &&
      maafwConfig.Info.Path &&
      normalizeProgressPath(data.project_path) !== normalizeProgressPath(maafwConfig.Info.Path)
    ) {
      return
    }

    const stage = String(data.stage || '')
    const status = String(data.status || '').toLowerCase()
    const terminalEvent = stage === 'completed' || stage === 'failed'
    if (
      !terminalEvent &&
      !agentEnvLoading.value &&
      (agentEnvProgressStatus.value === 'completed' || agentEnvProgressStatus.value === 'failed')
    ) {
      return
    }

    const percent = toProgressNumber(data.percent)
    const downloadedBytes = toProgressNumber(data.downloaded_bytes)
    const totalBytes = toProgressNumber(data.total_bytes)
    agentEnvProgressStage.value =
      AGENT_ENV_STAGE_LABELS[stage] || data.message || stage || '正在准备 MaaFW 运行环境'
    agentEnvProgressMessage.value = data.message || ''
    if (percent !== null) {
      agentEnvProgressPercent.value = Math.min(Math.max(percent, 0), 100)
    }
    if (downloadedBytes !== null) agentEnvProgressDownloadedBytes.value = downloadedBytes
    if (totalBytes !== null) agentEnvProgressTotalBytes.value = totalBytes
    if (Array.isArray(data.logs)) agentEnvProgressLogs.value = data.logs.map(String)

    if (stage === 'failed' || status === 'failed' || status === 'error') {
      agentEnvProgressStatus.value = 'failed'
      return
    }
    if (stage === 'completed' || status === 'completed' || status === 'ready') {
      agentEnvProgressStatus.value = 'completed'
      agentEnvProgressPercent.value = 100
      return
    }
    agentEnvProgressStatus.value = 'running'
  }

  const ensureProjectUpdateSubscription = () => {
    if (projectUpdateSubscriptionId) return
    projectUpdateSubscriptionId = subscribe(
      { id: scriptId, type: WS_MAAFW_PROJECT_UPDATE_PROGRESS },
      wsMessage => handleProjectUpdateProgress(wsMessage.data)
    )
  }

  const ensureAgentEnvProgressSubscription = () => {
    if (disposed || agentEnvProgressSubscriptionId) return
    agentEnvProgressSubscriptionId = subscribe(
      { id: scriptId, type: WS_MAAFW_ENV_PREPARE_PROGRESS },
      wsMessage => handleAgentEnvProgress(wsMessage.data)
    )
  }

  const resetProjectUpdateProgress = () => {
    projectUpdateStatus.value = 'running'
    projectUpdateStage.value = '正在准备更新检查'
    projectUpdateProgress.value = null
    projectUpdateDownloadPercent.value = null
    projectUpdateDownloadedBytes.value = null
    projectUpdateTotalBytes.value = null
    projectUpdateMessage.value = ''
    projectUpdateProviderErrorCode.value = null
    projectUpdateDiscoveredVersion.value = ''
    projectUpdateMetadataSource.value = ''
    projectUpdatePackageSource.value = ''
    projectUpdateLogs.value = []
  }

  const markProjectUpdateFailed = (reason: string) => {
    projectUpdateStatus.value = 'failed'
    projectUpdateStage.value = '项目更新失败'
    projectUpdateMessage.value = reason
  }

  const clearAgentEnvUiState = () => {
    agentEnvResult.value = null
    agentEnvProgressStatus.value = 'idle'
    agentEnvProgressStage.value = ''
    agentEnvProgressPercent.value = null
    agentEnvProgressMessage.value = ''
    agentEnvProgressLogs.value = []
    agentEnvProgressDownloadedBytes.value = null
    agentEnvProgressTotalBytes.value = null
  }

  const restorePreparedAgentEnv = async () => {
    if (disposed || !scriptId) return false
    const data = await prepareAgentEnv(maafwConfig.Info.Path, scriptId, {
      isActive: () => !disposed,
      notify: false,
      cacheOnly: true,
    })
    if (!data || disposed) return false

    if (formData.type === 'MaaFWManaged' && data.path && data.path !== maafwConfig.Info.Path) {
      maafwConfig.Info.Path = data.path
      await refreshPreviewIfPossible()
      if (disposed) return false
    }
    agentEnvResult.value = data
    agentEnvProgressStatus.value = 'completed'
    agentEnvProgressStage.value = '运行环境准备完成'
    agentEnvProgressPercent.value = 100
    agentEnvProgressMessage.value = data.message || '复用已准备的 MaaFW 运行环境'
    agentEnvProgressLogs.value = [...data.logs]
    return true
  }

  // ---- Action handlers ----

  const handlePreviewInterface = async () => {
    if (disposed) return
    if (isAgentEnvPreparing.value || isProjectUpdateRunning.value) return
    if (!maafwConfig.Info.Path) {
      message.warning('请先选择 MaaFramework 项目目录')
      return
    }

    const data = await previewInterface(maafwConfig.Info.Path)
    if (disposed) return
    if (data) {
      previewData.value = data
      await syncScriptNameFromProject(data)
      await syncProjectLabelFromProject(data)
      syncControllerResourceSelection(!isInitializing.value)
      await prunePeriodTaskSelections()
      if (disposed) return
      message.success(`已读取 ${previewProjectTitle.value}`)
      await handlePrepareAgentEnv()
    }
  }

  const handlePrepareAgentEnv = async () => {
    if (disposed) return
    if (isProjectUpdateRunning.value) return
    const isManagedProject = formData.type === 'MaaFWManaged'
    if (!maafwConfig.Info.Path && !isManagedProject) {
      message.warning('请先选择 MaaFramework 项目目录')
      return
    }

    const targetPath = maafwConfig.Info.Path
    const readyPath = agentEnvResult.value?.path || ''
    if (
      agentEnvResult.value &&
      agentEnvResult.value.status !== 'error' &&
      readyPath &&
      normalizeProgressPath(readyPath) === normalizeProgressPath(targetPath)
    ) {
      return
    }
    while (agentEnvPrepareRequest) {
      const activeRequest = agentEnvPrepareRequest
      await activeRequest.promise
      if (disposed) return
      if (activeRequest.path === targetPath || maafwConfig.Info.Path !== targetPath) {
        return
      }
    }

    const generation = ++agentEnvGeneration
    const isRequestAlive = () => !disposed && generation === agentEnvGeneration
    const isCurrentRequest = () =>
      isRequestAlive() &&
      (isManagedProject
        ? !targetPath || maafwConfig.Info.Path === targetPath
        : maafwConfig.Info.Path === targetPath)

    agentEnvResult.value = null
    ensureAgentEnvProgressSubscription()
    agentEnvProgressStatus.value = 'running'
    agentEnvProgressStage.value = '正在准备 MaaFW 运行环境'
    agentEnvProgressPercent.value = null
    agentEnvProgressMessage.value = '正在检查 Runner 与项目 Agent 依赖'
    agentEnvProgressLogs.value = []
    agentEnvProgressDownloadedBytes.value = null
    agentEnvProgressTotalBytes.value = null
    const promise = (async () => {
      const data = await prepareAgentEnv(targetPath, scriptId, {
        isActive: isRequestAlive,
        notify: false,
      })
      if (!isCurrentRequest()) return

      if (!data) {
        agentEnvResult.value = {
          path: targetPath,
          agentCount: 0,
          agents: [],
          logs: [],
          status: 'error',
          message: 'MaaFW 运行环境准备失败',
        }
        agentEnvProgressStatus.value = 'failed'
        agentEnvProgressStage.value = '运行环境准备失败'
        agentEnvProgressMessage.value = 'MaaFW 运行环境准备失败'
        message.error('MaaFW 运行环境准备失败')
        return
      }

      if (isManagedProject && data.path && data.path !== maafwConfig.Info.Path) {
        maafwConfig.Info.Path = data.path
        await refreshPreviewIfPossible()
        if (disposed) return
      }
      agentEnvResult.value = data
      agentEnvProgressLogs.value = [...data.logs]
      if (data.status === 'error') {
        agentEnvProgressStatus.value = 'failed'
        agentEnvProgressStage.value = '运行环境准备失败'
        agentEnvProgressMessage.value = data.message || 'MaaFW 运行环境准备失败'
        message.error(data.message || 'MaaFW 运行环境准备失败')
        return
      }
      agentEnvProgressStatus.value = 'completed'
      agentEnvProgressStage.value = '运行环境准备完成'
      agentEnvProgressPercent.value = 100
      agentEnvProgressMessage.value = data.message || 'MaaFW Runner 与 Agent 环境已就绪'
      if (data.agentCount === 0) {
        message.info('MaaFW Runner 环境已准备完成，当前项目没有声明 Agent')
        return
      }
      message.success(`MaaFW 运行环境已准备完成，共 ${data.agentCount} 个 Agent`)
    })()
    const request = { path: targetPath, generation, promise }
    agentEnvPrepareRequest = request
    try {
      await promise
    } finally {
      if (agentEnvPrepareRequest === request) agentEnvPrepareRequest = null
    }
  }

  const handleManualProjectUpdate = async () => {
    if (!maafwConfig.Info.Path) {
      message.warning('请先选择 MaaFramework 项目目录')
      return
    }
    if (!previewData.value) {
      message.warning('请先读取 interface')
      return
    }
    if (isAutoUpdateDisabled.value) {
      message.warning('当前脚本未声明版本，无法判断更新')
      return
    }
    if (
      isSaving.value ||
      hasUnsavedChanges.value ||
      isAgentEnvPreparing.value ||
      isProjectUpdateRunning.value
    ) {
      return
    }
    ensureProjectUpdateSubscription()
    const applyUpdate = projectUpdateAction.value === 'apply'
    resetProjectUpdateProgress()
    try {
      projectUpdateStage.value = applyUpdate ? '正在检查并应用项目资源更新' : '正在检查项目资源更新'
      const response = await updateProjectResources(scriptId, applyUpdate)
      projectUpdateLogs.value = response?.data?.logs ?? []
      const updateData = response?.data
      projectUpdateProviderErrorCode.value =
        typeof updateData?.providerErrorCode === 'number' ? updateData.providerErrorCode : null
      if (updateData?.updated) clearAgentEnvUiState()
      if (updateData?.latestVersion) {
        projectUpdateDiscoveredVersion.value = updateData.latestVersion
      }
      if (updateData?.source && (updateData.updated || updateData.installable)) {
        projectUpdatePackageSource.value = updateData.source
      }

      if (updateData?.updated) {
        const updatedWithWarning = response?.code !== 200 || response?.status !== 'success'
        projectUpdateAction.value = 'check'
        projectUpdateStage.value = '项目已更新，正在刷新 interface'
        const refreshed = await refreshPreviewIfPossible(true, updateData.latestVersion)
        await restorePreparedAgentEnv()
        projectUpdateStatus.value = 'completed'
        projectUpdateStage.value = updatedWithWarning
          ? '项目资源已更新，运行环境需要处理'
          : refreshed
            ? '项目资源与 interface 已刷新'
            : '项目资源已更新，interface 已按返回版本刷新'
        projectUpdateProgress.value = 100
        projectUpdateMessage.value = response?.message || 'MaaFW 项目资源已更新'
        if (updatedWithWarning) {
          message.warning(projectUpdateMessage.value)
        } else {
          message.success('MaaFW 项目资源已更新')
        }
        return
      }

      if (!response || response.code !== 200 || !updateData) {
        markProjectUpdateFailed(response?.message || 'MaaFW 项目更新失败')
        return
      }

      if (!applyUpdate && updateData.checked) {
        projectUpdateAction.value =
          updateData.updateAvailable && updateData.installable ? 'apply' : 'check'
        await refreshPreviewIfPossible()
        projectUpdateStatus.value = 'completed'
        projectUpdateStage.value = updateData.updateAvailable
          ? updateData.installable
            ? '已发现可安装更新，请再次点击“开始更新”'
            : '已发现更新，但当前来源没有可安装包'
          : '项目更新检查已完成'
        projectUpdateProgress.value = 100
        projectUpdateMessage.value = response.message || 'MaaFW 项目更新检查已完成'
        message.info(projectUpdateMessage.value)
        return
      }

      await refreshPreviewIfPossible()
      projectUpdateAction.value = 'check'
      projectUpdateStatus.value = 'completed'
      projectUpdateStage.value = '项目更新检查已完成'
      projectUpdateProgress.value = 100
      projectUpdateMessage.value = response.message || 'MaaFW 项目已是最新'
      message.info(response.message || 'MaaFW 项目已是最新')
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      logger.error(`MaaFW 项目更新失败: ${reason}`)
      markProjectUpdateFailed(reason || 'MaaFW 项目更新失败')
    } finally {
      if (projectUpdateStatus.value === 'running') {
        markProjectUpdateFailed('MaaFW 项目更新未正常完成')
      }
    }
  }

  const refreshPreviewIfPossible = async (
    forceUiRefresh = false,
    fallbackVersion?: string | null
  ): Promise<boolean> => {
    if (!maafwConfig.Info.Path) return false
    const previousData = previewData.value
    const data = await previewInterface(maafwConfig.Info.Path)
    if (data) {
      previewData.value = data
      await syncScriptNameFromProject(data)
      await syncProjectLabelFromProject(data)
      syncControllerResourceSelection(!isInitializing.value)
      await prunePeriodTaskSelections()
      return true
    }
    if (forceUiRefresh && previousData) {
      previewData.value = {
        ...previousData,
        project: {
          ...previousData.project,
          version: fallbackVersion || previousData.project.version,
        },
      }
    }
    return false
  }

  const loadGlobalUpdateDefaults = async () => {
    const settings = await getSettings()
    globalUpdateSource.value = settings?.Update?.Source || ''
    globalUpdateChannel.value = settings?.Update?.Channel || ''
    globalMirrorChyanCDK.value = settings?.Update?.MirrorChyanCDK || ''
  }

  const loadEmulatorOptions = async () => {
    if (emulatorOptionsLoaded) {
      emulatorOptionsReady.value = true
      return
    }
    if (emulatorOptionsPromise) return emulatorOptionsPromise

    const request = (async () => {
      emulatorLoading.value = true
      emulatorOptionsReady.value = false
      let comboLoaded = false
      let detailLoaded = false
      try {
        const [response, detailResponse] = await Promise.all([
          Service.getEmulatorComboxApiInfoComboxEmulatorPost(),
          Service.getEmulatorApiEmulatorGetPost({}),
        ])
        if (response?.code === 200) {
          emulatorOptions.value = response.data || []
          comboLoaded = true
        }
        if (detailResponse?.code === 200) {
          const typeMap: Record<string, EmulatorType> = {}
          Object.entries(detailResponse.data || {}).forEach(([emulatorId, config]) => {
            const emulatorType = config.Info?.Type
            if (emulatorType) typeMap[emulatorId] = emulatorType
          })
          emulatorTypeById.value = typeMap
          detailLoaded = true
        }
        if (comboLoaded) {
          // Warm every emulator's instance list while the script page is
          // loading.  Opening either selector is then a local read instead of
          // a visible network wait; the selected emulator still updates the
          // bound options in loadEmulatorDeviceOptions().
          const emulatorIds = emulatorOptions.value
            .map(item => String(item.value || '').trim())
            .filter((value): value is string => Boolean(value && value !== '-'))
          await Promise.all(emulatorIds.map(emulatorId => loadEmulatorDeviceOptions(emulatorId)))
        }
        emulatorOptionsLoaded = comboLoaded && detailLoaded
        emulatorOptionsReady.value = emulatorOptionsLoaded
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`加载模拟器选项失败: ${errorMsg}`)
        emulatorOptionsReady.value = false
      } finally {
        emulatorLoading.value = false
      }
    })()
    emulatorOptionsPromise = request
    try {
      await request
    } finally {
      if (emulatorOptionsPromise === request) emulatorOptionsPromise = null
    }
  }

  const loadEmulatorDeviceOptions = async (emulatorId: string) => {
    if (!emulatorId || emulatorId === '-') {
      emulatorDeviceOptions.value = []
      emulatorDeviceLoading.value = false
      return
    }

    const cachedOptions = emulatorDeviceOptionsCache.get(emulatorId)
    if (cachedOptions) {
      if (maafwConfig.Emulator.Id === emulatorId) {
        emulatorDeviceOptions.value = [...cachedOptions]
        emulatorDeviceLoading.value = false
      }
      return
    }

    emulatorDeviceLoading.value = true
    let request = emulatorDeviceRequests.get(emulatorId)
    if (!request) {
      request = (async () => {
        try {
          const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
            emulatorId,
          })
          if (response?.code !== 200) return null
          const options = response.data || []
          emulatorDeviceOptionsCache.set(emulatorId, [...options])
          return options
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : String(error)
          logger.error(`加载模拟器实例选项失败: ${errorMsg}`)
          return null
        }
      })()
      emulatorDeviceRequests.set(emulatorId, request)
    }
    try {
      const options = await request
      if (options && maafwConfig.Emulator.Id === emulatorId) {
        emulatorDeviceOptions.value = [...options]
      }
    } finally {
      if (emulatorDeviceRequests.get(emulatorId) === request) {
        emulatorDeviceRequests.delete(emulatorId)
      }
      if (maafwConfig.Emulator.Id === emulatorId) emulatorDeviceLoading.value = false
    }
  }

  const handleEmulatorSelectChange = async (emulatorId: string) => {
    maafwConfig.Emulator.Index = '-'
    emulatorDeviceOptions.value = []
    await handleChange('Emulator', 'Id', emulatorId)
    await handleChange('Emulator', 'Index', '-')
    await loadEmulatorDeviceOptions(emulatorId)
  }

  const selectMaaFWPath = async () => {
    try {
      const path = await window.electronAPI?.selectFolder()
      if (path) {
        maafwConfig.Info.Path = path
        agentEnvResult.value = null
        agentEnvProgressStatus.value = 'idle'
        agentEnvProgressStage.value = ''
        agentEnvProgressPercent.value = null
        agentEnvProgressMessage.value = ''
        agentEnvProgressLogs.value = []
        agentEnvProgressDownloadedBytes.value = null
        agentEnvProgressTotalBytes.value = null
        await handleChange('Info', 'Path', path)
        await handlePreviewInterface()
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`选择 MaaFW 项目目录失败: ${errorMsg}`)
      message.error('选择文件夹失败')
    }
  }

  const selectGamePath = async () => {
    try {
      const paths = await window.electronAPI?.selectFile([
        {
          name: 'Executable',
          extensions: ['exe'],
        },
      ])
      const path = paths?.[0]
      if (!path) return

      const fileName = path.split(/[\\/]/).pop() || ''
      if (!fileName.toLowerCase().endsWith('.exe')) {
        message.error('请选择游戏 exe 文件')
        return
      }

      maafwConfig.Game.Path = path
      await handleChange('Game', 'Path', path)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`选择游戏可执行文件失败: ${errorMsg}`)
      message.error('选择游戏可执行文件失败')
    }
  }

  /**
   * 加载脚本配置。不设置 isSetupMode，不处理路由跳转。
   * 失败时调用 message.error 后抛出异常，由调用方决定是否重定向。
   */
  const loadScript = async () => {
    pageLoading.value = true
    try {
      await loadGlobalUpdateDefaults()

      const routeState = history.state as { scriptData?: { config?: MaaFWScriptConfig } }
      if (routeState?.scriptData) {
        applyScriptConfig(routeState.scriptData.config)
      }

      const scriptDetail = (await registryApi.getScripts(scriptId))[0]
      if (!scriptDetail) {
        message.error('脚本不存在或加载失败')
        throw new Error('脚本不存在或加载失败')
      }

      formData.type = scriptDetail.type as ScriptType
      scriptEditHint.value = scriptDetail.edit_hint ?? null
      scriptIconUrl.value = scriptDetail.icon_url ?? null
      applyScriptConfig(scriptDetail.config as MaaFWScriptConfig)

      if (maafwConfig.Emulator.Id && maafwConfig.Emulator.Id !== '-') {
        await loadEmulatorDeviceOptions(maafwConfig.Emulator.Id)
      }
      await refreshPreviewIfPossible()
      await restorePreparedAgentEnv()
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载脚本失败: ${errorMsg}`)
      if (errorMsg !== '脚本不存在或加载失败') {
        message.error('加载脚本失败')
      }
      throw error
    } finally {
      pageLoading.value = false
    }
  }

  /** 清理页面订阅；后台保存与环境预热请求继续执行，但不再回写页面状态。 */
  const dispose = () => {
    if (disposed) return
    disposed = true
    agentEnvGeneration += 1
    if (saveStatusTimer) {
      clearTimeout(saveStatusTimer)
      saveStatusTimer = null
    }
    if (projectUpdateSubscriptionId) {
      unsubscribe(projectUpdateSubscriptionId)
      projectUpdateSubscriptionId = null
    }
    if (agentEnvProgressSubscriptionId) {
      unsubscribe(agentEnvProgressSubscriptionId)
      agentEnvProgressSubscriptionId = null
    }
  }

  const handleBeforeUnload = (event: BeforeUnloadEvent) => {
    if (!hasUnsavedChanges.value && !isSaving.value) return
    event.preventDefault()
    event.returnValue = ''
  }

  return {
    // core state
    maafwConfig,
    formData,
    rules,
    previewData,
    agentEnvResult,
    agentEnvProgressStatus,
    agentEnvProgressStage,
    agentEnvProgressPercent,
    agentEnvProgressMessage,
    agentEnvProgressLogs,
    agentEnvProgressDownloadedBytes,
    agentEnvProgressTotalBytes,
    projectUpdateLogs,
    projectUpdateAction,
    projectUpdateStatus,
    projectUpdateStage,
    projectUpdateProgress,
    projectUpdateDownloadPercent,
    projectUpdateDownloadedBytes,
    projectUpdateTotalBytes,
    projectUpdateMessage,
    projectUpdateProviderErrorCode,
    projectUpdateDiscoveredVersion,
    projectUpdateMetadataSource,
    projectUpdatePackageSource,
    scriptEditHint,
    scriptIconUrl,
    // loading / save state
    pageLoading,
    isInitializing,
    isSaving,
    saveStatus,
    saveErrorMessage,
    hasUnsavedChanges,
    interfaceLoading,
    agentEnvLoading,
    projectUpdateLoading,
    emulatorLoading,
    emulatorOptionsReady,
    emulatorDeviceLoading,
    // emulator state
    emulatorOptions,
    emulatorDeviceOptions,
    emulatorTypeById,
    // period task state
    dailyOnceTasks,
    weeklyOnceTasks,
    monthlyOnceTasks,
    // computed: derived state
    isAutoUpdateDisabled,
    isInterfaceReady,
    isAgentEnvReady,
    isAgentEnvFailed,
    isAgentEnvPreparing,
    hasEffectiveMirrorChyanCDK,
    projectUpdateMirrorSourceBlocked,
    isProjectUpdateRunning,
    projectUpdateDisabled,
    periodTaskOptions,
    previewProjectTitle,
    interfaceStats,
    // computed: controller / resource
    controllerOptions,
    directControllerOptions,
    unsupportedControllerOptions,
    unsupportedControllerMessage,
    effectiveControllerName,
    effectiveController,
    effectiveControllerType,
    isAdbController,
    isDesktopController,
    resourceOptions,
    interfaceDependentDisabled,
    // computed: emulator strategy
    selectedEmulatorType,
    selectedEmulatorLabel,
    selectedEmulatorCapability,
    adbControlStrategyMessage,
    adbControlStrategyItems,
    // computed: agent env
    agentEnvAlertType,
    agentEnvSummary,
    agentEnvDescription,
    agentEnvChecklistDescription,
    // static options
    updateSourceOptions,
    updateChannelOptions,
    // functions
    setSaveStatus,
    copyToClipboard,
    handleChange,
    handlePeriodTaskChange,
    handlePreviewInterface,
    handlePrepareAgentEnv,
    handleManualProjectUpdate,
    refreshPreviewIfPossible,
    handleControllerChange,
    handleResourceChange,
    handleEmulatorSelectChange,
    selectMaaFWPath,
    selectGamePath,
    loadScript,
    loadEmulatorOptions,
    loadEmulatorDeviceOptions,
    handleBeforeUnload,
    dispose,
  }
}

export type MaaFWScriptConfigState = ReturnType<typeof useMaaFWScriptConfig>

export type { MaaFWControllerInfo }
