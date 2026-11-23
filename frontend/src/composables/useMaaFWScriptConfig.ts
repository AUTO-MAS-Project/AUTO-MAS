import { translate as t } from '@/i18n'
import { computed, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import { useGamesApi, useGameBindingQuery } from '@/composables/useGamesApi'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'

const logger = window.electronAPI.getLogger('MaaFW脚本编辑')

type MaaFWProjectUpdateSource = MaaFWScriptConfig['Update']['Source']
type MaaFWProjectUpdateChannel = MaaFWScriptConfig['Update']['Channel']

const MAAFW_DIRECT_CONTROLLER_TYPES = ['Adb', 'Win32'] as const
type MaaFWDirectControllerType = (typeof MAAFW_DIRECT_CONTROLLER_TYPES)[number]

export const isDirectControllerType = (
  controllerType?: string | null
): controllerType is MaaFWDirectControllerType =>
  MAAFW_DIRECT_CONTROLLER_TYPES.includes(controllerType as MaaFWDirectControllerType)

/**
 * 项目更新的下载源，由用户显式选择，没有「自动」：选 Mirror 酱就得自己填 CDK，
 * CDK 不可用时后端明确报错而不是悄悄换成 GitHub。两项须与后端
 * MaaFWConfig.Update.Source 的 OptionsValidator 一致。
 */
const UPDATE_SOURCES = [
  'MirrorChyan',
  'GitHub',
] as const satisfies readonly MaaFWProjectUpdateSource[]

/** 项目更新通道只有稳定版 / 测试版，没有「跟随全局」，也故意不开放 alpha。 */
const UPDATE_CHANNELS = ['stable', 'beta'] as const satisfies readonly MaaFWProjectUpdateChannel[]

// 下拉选项的文案随界面语言变，所以是 computed
export const updateSourceOptions = computed(() => [
  { label: t('core.edit.sourceMirrorChyan'), value: 'MirrorChyan' },
  { label: t('core.edit.sourceGithub'), value: 'GitHub' },
])

export const updateChannelOptions = computed(() => [
  { label: t('core.edit.maafwUpdateChannelStable'), value: 'stable' },
  { label: t('core.edit.maafwUpdateChannelBeta'), value: 'beta' },
])

export const isMaaFWUpdateSource = (value: unknown): value is MaaFWProjectUpdateSource =>
  (UPDATE_SOURCES as readonly unknown[]).includes(value)

export const isMaaFWUpdateChannel = (value: unknown): value is MaaFWProjectUpdateChannel =>
  (UPDATE_CHANNELS as readonly unknown[]).includes(value)

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
  game: { game_id: '-', device_id: '-' },
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
    LaunchMode: 'DirectExe',
    LaunchPath: '',
    LauncherPath: '',
    URL: '',
    CloseMode: 'OnFailure',
    PackageName: '',
    Arguments: '',
    WaitTime: 120,
    UnityResolution: 'Off',
    Hotkeys: '{}',
  },
  Update: {
    PackageMode: 'incremental',
    AutoUpdateMode: 'BeforeRun',
    Source: 'GitHub',
    Channel: 'stable',
    MirrorChyanCDK: '',
    ProxyAddress: '',
  },
  Embedded: {
    SourceVersion: '',
    ImportedAt: null,
    Report: '{ }',
    FollowSource: false,
  },
  Run: {
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    RunTimeLimit: 120,
    DailyOnceTasks: '[ ]',
    WeeklyOnceTasks: '[ ]',
    MonthlyOnceTasks: '[ ]',
    TaskTimeLimit: 45,
    TaskTimeLimitOverrides: '{ }',
    LoopGuard: true,
    GameUpdateMode: 'Off',
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
 *
 * ModAVD 对所有 MFW 脚本（通用项目与各特调）放行，设备下拉原样列出它的实例。
 */
export function useMaaFWControlConfig(
  maafwConfig: MaaFWScriptConfig,
  previewData: Ref<MaaFWInterfacePreviewData | null>,
  interfaceLoading: Ref<boolean>,
  handleChange: PersistFn
) {
  const route = useRoute()
  const scriptId = computed(() => String(route.params.id ?? route.params.scriptId ?? ''))
  const games = useGamesApi()
  const binding = useGameBindingQuery(scriptId)
  const selectedGame = computed(() =>
    games.rows.value.find(
      game => game.uid === (binding.data.value?.binding?.game_id ?? maafwConfig.game.game_id)
    )
  )

  // ---- Controller / Resource helpers ----

  const controllerOptions = computed(() => previewData.value?.controllers || [])
  const directControllerOptions = computed(() =>
    controllerOptions.value.filter(controller => isDirectControllerType(controller.type))
  )
  const getDefaultControllerName = () => {
    const wantsAdb = selectedGame.value?.type.kind === 'emulator'
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

  const effectiveResourceName = computed(() => resolveResourceName(maafwConfig.Info.Resource))

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

  // 能力由选中安装的适配插件决定，不再通过聚合模拟器槽位反查。
  const selectedCapabilityType = computed(() =>
    selectedGame.value?.type.kind === 'emulator'
      ? selectedGame.value.type.type === 'general_emulator'
        ? 'general'
        : selectedGame.value.type.type
      : undefined
  )
  const selectedEmulatorCapability = computed(() => {
    const type = selectedCapabilityType.value
    return type ? (previewData.value?.controlCapabilities.emulatorExtras[type] ?? null) : null
  })

  const adbControlStrategyItems = computed(() => {
    const capability = selectedEmulatorCapability.value
    const screencapWithExtras = Boolean(capability?.screencap)
    const inputWithExtras = Boolean(capability?.input)

    // 只列截图与输入两行，值只给一个词：模拟器是上面刚选的，不必再重复；集合怎么组的不解释
    // ModAVD 的 EmulatorExtras（AVDExtras）截图走共享内存，不是 adb，不能套雷电 / MuMu 那句
    const extrasText =
      selectedCapabilityType.value === 'avd'
        ? t('core.edit.adbStrategyAvdExtras')
        : t('core.edit.adbStrategyEmulatorExtras')
    const pick = (withExtras: boolean) =>
      withExtras ? extrasText : t('core.edit.adbStrategyDefault')
    return [
      { label: t('core.misc.screenshot'), value: pick(screencapWithExtras) },
      { label: t('core.misc.input'), value: pick(inputWithExtras) },
    ]
  })

  // 游戏 exe 与启动器 exe 共用同一个选择流程，只差写回哪个字段
  const selectGameExePath = async (key: 'LaunchPath' | 'LauncherPath') => {
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
        message.error(t('core.misc.pickExeFile'))
        return
      }

      maafwConfig.Game[key] = path
      await handleChange('Game', key, path)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`选择 ${key} exe 失败: ${errorMsg}`)
      message.error(t('core.misc.couldNotPickLaunch'))
    }
  }

  const selectLaunchPath = () => selectGameExePath('LaunchPath')
  const selectLauncherPath = () => selectGameExePath('LauncherPath')

  return {
    prepareBinding: () => Promise.all([binding.refetch({ cancelRefetch: false }), games.prepare()]),
    controllerOptions,
    effectiveControllerName,
    effectiveControllerType,
    isAdbController,
    isDesktopController,
    resourceOptions,
    effectiveResourceName,
    interfaceDependentDisabled,
    adbControlStrategyItems,
    resolveControllerName,
    resolveResourceName,
    handleControllerChange,
    handleResourceChange,
    syncControllerResourceSelection,
    selectLaunchPath,
    selectLauncherPath,
  }
}
