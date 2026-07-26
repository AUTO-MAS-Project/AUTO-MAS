import { computed, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ComboBoxItem } from '@/api'
import { useMaaFWApi } from '@/composables/useMaaFWApi'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useSettingsApi } from '@/composables/useSettingsApi'
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

type MaaFWConcreteUpdateSource = Exclude<MaaFWScriptConfig['Update']['Source'], ''>
type MaaFWConcreteUpdateChannel = Exclude<MaaFWScriptConfig['Update']['Channel'], ''>

const MAAFW_UPDATE_SOURCES: MaaFWConcreteUpdateSource[] = ['MirrorChyan', 'GitHub']
const MAAFW_UPDATE_CHANNELS: MaaFWConcreteUpdateChannel[] = ['stable', 'beta']
const MAAFW_DIRECT_CONTROLLER_TYPES = ['Adb', 'Win32'] as const

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

const isMaaFWUpdateSource = (value: string): value is MaaFWConcreteUpdateSource =>
  MAAFW_UPDATE_SOURCES.includes(value as MaaFWConcreteUpdateSource)

const isMaaFWUpdateChannel = (value: string): value is MaaFWConcreteUpdateChannel =>
  MAAFW_UPDATE_CHANNELS.includes(value as MaaFWConcreteUpdateChannel)

const updateSourceOptions = MAAFW_UPDATE_SOURCES.map(value => ({ label: value, value }))

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
    Source: 'MirrorChyan',
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
  const pendingSave = ref<{
    category: keyof MaaFWScriptConfig
    key: string
    value: unknown
    force: boolean
  } | null>(null)
  const previewData = ref<MaaFWInterfacePreviewData | null>(null)
  const agentEnvResult = ref<MaaFWAgentEnvPrepareData | null>(null)
  const scriptEditHint = ref<Script['editHint']>(null)
  const scriptIconUrl = ref<string | null>(null)
  const dailyOnceTasks = ref<string[]>([])
  const weeklyOnceTasks = ref<string[]>([])
  const monthlyOnceTasks = ref<string[]>([])
  const globalUpdateSource = ref<string>('')
  const globalUpdateChannel = ref<string>('')
  let saveStatusTimer: ReturnType<typeof setTimeout> | null = null

  const emulatorLoading = ref(false)
  const emulatorDeviceLoading = ref(false)
  const emulatorOptions = ref<ComboBoxItem[]>([])
  const emulatorDeviceOptions = ref<ComboBoxItem[]>([])
  const emulatorTypeById = ref<Record<string, EmulatorType>>({})

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

  const projectUpdateDisabled = computed(
    () =>
      !maafwConfig.Info.Path ||
      !previewData.value ||
      isAutoUpdateDisabled.value ||
      isSaving.value ||
      interfaceLoading.value ||
      projectUpdateLoading.value
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
    if (saveStatusTimer) {
      clearTimeout(saveStatusTimer)
      saveStatusTimer = null
    }
    saveStatus.value = status
    saveErrorMessage.value = errorMessage
    if (status === 'saved') {
      saveStatusTimer = setTimeout(() => {
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

  const resolveUpdateSource = (value?: string | null): MaaFWConcreteUpdateSource => {
    if (value && isMaaFWUpdateSource(value)) return value
    if (globalUpdateSource.value && isMaaFWUpdateSource(globalUpdateSource.value)) {
      return globalUpdateSource.value
    }
    return MAAFW_UPDATE_SOURCES[0]
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
    dailyOnceTasks.value = parseTaskNameList(normalized.Run.DailyOnceTasks)
    weeklyOnceTasks.value = parseTaskNameList(normalized.Run.WeeklyOnceTasks)
    monthlyOnceTasks.value = parseTaskNameList(normalized.Run.MonthlyOnceTasks)
    maafwConfig.Run.DailyOnceTasks = stringifyTaskNameList(dailyOnceTasks.value)
    maafwConfig.Run.WeeklyOnceTasks = stringifyTaskNameList(weeklyOnceTasks.value)
    maafwConfig.Run.MonthlyOnceTasks = stringifyTaskNameList(monthlyOnceTasks.value)
  }

  const updateScriptConfig = async (config: Record<string, unknown>) => {
    try {
      await registryApi.updateScript(scriptId, config)
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      message.error(errorMsg)
      return false
    }
  }

  const handleChange = async (
    category: keyof MaaFWScriptConfig,
    key: string,
    value: unknown,
    force = false
  ) => {
    if ((!force && isInitializing.value) || isSaving.value) {
      if (isSaving.value) {
        pendingSave.value = { category, key, value, force }
      }
      return
    }

    hasUnsavedChanges.value = true
    setSaveStatus('saving')
    isSaving.value = true
    try {
      const success = await updateScriptConfig({ [category]: { [key]: value } })
      if (success) {
        logger.info(`配置已保存: ${category}.${key}`)
        hasUnsavedChanges.value = false
        setSaveStatus('saved')
      } else {
        setSaveStatus('error')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
      setSaveStatus('error', `保存失败：${errorMsg}`)
    } finally {
      isSaving.value = false
      if (pendingSave.value) {
        const pending = pendingSave.value
        pendingSave.value = null
        void handleChange(pending.category, pending.key, pending.value, pending.force)
      }
    }
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

  // ---- Action handlers ----

  const handlePreviewInterface = async () => {
    if (!maafwConfig.Info.Path) {
      message.warning('请先选择 MaaFramework 项目目录')
      return
    }

    const data = await previewInterface(maafwConfig.Info.Path)
    if (data) {
      previewData.value = data
      await syncScriptNameFromProject(data)
      await syncProjectLabelFromProject(data)
      syncControllerResourceSelection(!isInitializing.value)
      await prunePeriodTaskSelections()
      message.success(`已读取 ${previewProjectTitle.value}`)
    }
  }

  const handlePrepareAgentEnv = async () => {
    if (!maafwConfig.Info.Path) {
      message.warning('请先选择 MaaFramework 项目目录')
      return
    }

    agentEnvResult.value = null
    const data = await prepareAgentEnv(maafwConfig.Info.Path)
    if (!data) return

    agentEnvResult.value = data
    if (data.status === 'error') {
      message.error(data.message || 'MaaFW 运行环境准备失败')
      return
    }
    if (data.agentCount === 0) {
      message.info('MaaFW Runner 环境已准备完成，当前项目没有声明 Agent')
      return
    }
    message.success(`MaaFW 运行环境已准备完成，共 ${data.agentCount} 个 Agent`)
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
    if (isSaving.value || projectUpdateLoading.value) return

    isSaving.value = true
    try {
      const saved = await updateScriptConfig({
        Update: { ...maafwConfig.Update },
      })
      if (!saved) return
    } finally {
      isSaving.value = false
    }

    let response: Awaited<ReturnType<typeof updateProjectResources>>
    try {
      response = await updateProjectResources(scriptId)
    } catch {
      message.error('MaaFW 项目资源更新失败，请检查网络、更新源和项目配置')
      return
    }
    if (!response?.data || response.code !== 200) {
      message.error(response?.message || 'MaaFW 项目资源更新失败，请检查项目配置')
      return
    }

    await refreshPreviewIfPossible()
    if (response.data.updated) {
      message.success(response.message || 'MaaFW 项目资源已更新')
      return
    }

    message.info(response.message || 'MaaFW 项目已是最新')
  }

  const refreshPreviewIfPossible = async () => {
    if (!maafwConfig.Info.Path) return
    const data = await previewInterface(maafwConfig.Info.Path)
    if (data) {
      previewData.value = data
      await syncScriptNameFromProject(data)
      await syncProjectLabelFromProject(data)
      syncControllerResourceSelection(!isInitializing.value)
      await prunePeriodTaskSelections()
    }
  }

  const loadGlobalUpdateDefaults = async () => {
    const settings = await getSettings()
    globalUpdateSource.value = settings?.Update?.Source || ''
    globalUpdateChannel.value = settings?.Update?.Channel || ''
  }

  const loadEmulatorOptions = async () => {
    emulatorLoading.value = true
    try {
      const [response, detailResponse] = await Promise.all([
        Service.getEmulatorComboxApiInfoComboxEmulatorPost(),
        Service.getEmulatorApiEmulatorGetPost({}),
      ])
      if (response?.code === 200) {
        emulatorOptions.value = response.data || []
      }
      if (detailResponse?.code === 200) {
        const typeMap: Record<string, EmulatorType> = {}
        Object.entries(detailResponse.data || {}).forEach(([emulatorId, config]) => {
          const emulatorType = config.Info?.Type
          if (emulatorType) typeMap[emulatorId] = emulatorType
        })
        emulatorTypeById.value = typeMap
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载模拟器选项失败: ${errorMsg}`)
    } finally {
      emulatorLoading.value = false
    }
  }

  const loadEmulatorDeviceOptions = async (emulatorId: string) => {
    if (!emulatorId || emulatorId === '-') return

    emulatorDeviceLoading.value = true
    try {
      const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
        emulatorId,
      })
      if (response?.code === 200) {
        emulatorDeviceOptions.value = response.data || []
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载模拟器实例选项失败: ${errorMsg}`)
    } finally {
      emulatorDeviceLoading.value = false
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

  /** 清理定时器，供页面在 onBeforeUnmount 中调用 */
  const dispose = () => {
    if (saveStatusTimer) {
      clearTimeout(saveStatusTimer)
      saveStatusTimer = null
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
