import { computed, ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ComboBoxItem } from '@/api'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'

const logger = window.electronAPI.getLogger('MaaFW脚本编辑')

export type EmulatorType = 'general' | 'mumu' | 'ldplayer'

const EMULATOR_TYPE_LABELS: Record<EmulatorType, string> = {
  general: '通用模拟器',
  mumu: 'MuMu 模拟器',
  ldplayer: '雷电模拟器',
}

type MaaFWProjectUpdateSource = MaaFWScriptConfig['Update']['Source']
type MaaFWConcreteUpdateChannel = Exclude<MaaFWScriptConfig['Update']['Channel'], ''>

const MAAFW_DIRECT_CONTROLLER_TYPES = ['Adb', 'Win32'] as const
type MaaFWDirectControllerType = (typeof MAAFW_DIRECT_CONTROLLER_TYPES)[number]

export const isDirectControllerType = (
  controllerType?: string | null
): controllerType is MaaFWDirectControllerType =>
  MAAFW_DIRECT_CONTROLLER_TYPES.includes(controllerType as MaaFWDirectControllerType)

export const updateSourceOptions = [
  { label: '自动', value: '' },
  { label: 'MirrorChyan', value: 'MirrorChyan' },
  { label: 'GitHub', value: 'GitHub' },
] satisfies Array<{ label: string; value: MaaFWProjectUpdateSource }>

export const updateChannelOptions = [
  { label: '跟随全局', value: '' as MaaFWScriptConfig['Update']['Channel'] },
  { label: '稳定版', value: 'stable' as MaaFWConcreteUpdateChannel },
  { label: '测试版', value: 'beta' as MaaFWConcreteUpdateChannel },
]

/**
 * MaaFW 脚本配置的默认形态。后端未返回某段时用它兜底，保证编辑页所有
 * 分组都可绑定。字段默认值与 app/models/config.py 的 MaaFWConfig 对齐。
 */
export const getDefaultMaaFWScriptConfig = (): MaaFWScriptConfig => ({
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
    LaunchMode: 'AttachOnly',
    LaunchPath: '',
    LaunchURL: '',
    Arguments: '',
    ProcessPath: '',
    ProcessName: '',
    WaitTime: 60,
    CloseOnFinish: true,
  },
  Update: {
    IfAutoUpdate: true,
    Source: '',
    Channel: '',
    MirrorChyanCDK: '',
    GitHubRepo: '',
    GitHubTag: '',
    GitHubAssetPattern: '',
  },
  Managed: {
    Enabled: false,
    ProjectId: '',
    StoreId: '',
    Version: '',
    RuntimeConstraint: '',
    ProjectManifest: '{ }',
    CheckoutPath: '',
    PendingUpgrade: '{ }',
    LastOperation: '{ }',
  },
  ManagedRuntime: {
    RuntimeId: '',
    PoolId: '',
    PythonExecutable: '',
    VenvPath: '',
    RuntimeBinding: '{ }',
  },
  ManagedRemote: {
    Source: 'MirrorChyan',
    Channel: 'stable',
    MirrorChyanRID: '',
    MirrorChyanCDK: '',
    GitHubRepo: '',
    GitHubTag: '',
    GitHubAssetPattern: '\\.zip$',
  },
  Run: {
    Engine: 'external',
    ProxyTimesLimit: 0,
    RunTimesLimit: 1,
    RunTimeLimit: 30,
    DailyOnceTasks: '[ ]',
    WeeklyOnceTasks: '[ ]',
    MonthlyOnceTasks: '[ ]',
  },
})

type PersistFn = (
  category: keyof MaaFWScriptConfig,
  key: string,
  value: unknown
) => unknown | Promise<unknown>

/**
 * 控制方式 / 模拟器 / 游戏生命周期配置的共享逻辑。
 *
 * 从 mfwa 的 useMaaFWScriptConfig.ts 摘取控制器解析、资源过滤、模拟器选项
 * 加载与 ADB 控制策略提示部分，去掉 managed / agent-env / progress-socket
 * 依赖，供 ControlConfigSection.vue 使用。
 */
export function useMaaFWControlConfig(
  maafwConfig: MaaFWScriptConfig,
  previewData: Ref<MaaFWInterfacePreviewData | null>,
  interfaceLoading: Ref<boolean>,
  handleChange: PersistFn
) {
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

  const syncControllerResourceSelection = async (persist = false) => {
    if (!previewData.value) return
    const nextController = resolveControllerName(maafwConfig.Info.Controller)
    const nextResource = resolveResourceName(maafwConfig.Info.Resource, nextController)
    const controllerChanged = maafwConfig.Info.Controller !== nextController
    const resourceChanged = maafwConfig.Info.Resource !== nextResource
    maafwConfig.Info.Controller = nextController
    maafwConfig.Info.Resource = nextResource
    if (persist && (controllerChanged || resourceChanged)) {
      if (controllerChanged) {
        await handleChange('Info', 'Controller', nextController)
      }
      if (resourceChanged) {
        await handleChange('Info', 'Resource', nextResource)
      }
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

  const selectLaunchPath = async () => {
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
        message.error('请选择 exe 文件')
        return
      }

      maafwConfig.Game.LaunchPath = path
      // 进程字段不再让用户填：DirectExe 直启游戏本体（LauncherExe 已下线），
      // 检测目标按定义就是启动目标，从所选 exe 推导即可。内置运行压根不读这
      // 两个键（runner_task 用 LaunchPath 做进程检测），保留它们只为第一层
      // 外部运行路径的 game_lifecycle 仍能读到。
      maafwConfig.Game.ProcessPath = path
      maafwConfig.Game.ProcessName = fileName
      await handleChange('Game', 'LaunchPath', path)
      // 这两个键此前靠输入框 @blur 落盘，输入框删掉后必须显式持久化，
      // 否则只改了内存、第一层读到的仍是旧值。
      await handleChange('Game', 'ProcessPath', path)
      await handleChange('Game', 'ProcessName', fileName)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`选择启动 exe 失败: ${errorMsg}`)
      message.error('选择启动 exe 失败')
    }
  }

  return {
    emulatorLoading,
    emulatorOptionsReady,
    emulatorDeviceLoading,
    emulatorOptions,
    emulatorDeviceOptions,
    emulatorTypeById,
    controllerOptions,
    unsupportedControllerOptions,
    unsupportedControllerMessage,
    effectiveControllerName,
    effectiveControllerType,
    isAdbController,
    isDesktopController,
    resourceOptions,
    interfaceDependentDisabled,
    selectedEmulatorLabel,
    adbControlStrategyMessage,
    adbControlStrategyItems,
    resolveControllerName,
    resolveResourceName,
    handleControllerChange,
    handleResourceChange,
    syncControllerResourceSelection,
    loadEmulatorOptions,
    loadEmulatorDeviceOptions,
    handleEmulatorSelectChange,
    selectLaunchPath,
  }
}
