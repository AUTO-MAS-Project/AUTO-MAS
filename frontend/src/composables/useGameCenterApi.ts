import { computed, reactive, ref } from 'vue'
import {
  Service,
  type ComboBoxItem,
  type EmulatorConfig,
  type EmulatorConfigIndexItem,
  type GameCheckOut,
  type GameConfig,
  type GameConfigIndexItem,
  type GamePresetItem,
  type GameProviderItem,
  type GameSignAccountsListOut,
  type GameTaskStatusOut,
} from '@/api'

const logger = window.electronAPI.getLogger('游戏中心')

export interface ManagedGame {
  id: string
  config: GameConfig
}

export interface GameSignAccountSummary {
  uid: string
  type: string
  name: string
  game: string
  enabled: boolean
}

export interface GameActionState {
  checking: boolean
  saving: boolean
  launching: boolean
  closing: boolean
  deleting: boolean
  installing: boolean
  canceling: boolean
}

const emptyActionState = (): GameActionState => ({
  checking: false,
  saving: false,
  launching: false,
  closing: false,
  deleting: false,
  installing: false,
  canceling: false,
})

const responseError = (message: string | null | undefined, fallback: string): Error =>
  new Error(message || fallback)

const readableGameCenterError = (cause: unknown, fallback = '加载游戏中心数据失败'): string => {
  const detail = cause instanceof Error ? cause.message : String(cause ?? '')
  if (/failed to fetch|networkerror|network request failed/i.test(detail)) {
    return '无法连接后端服务'
  }
  return detail.trim() || fallback
}

export const isMaaFWManagedIdentity = (...parts: Array<string | null | undefined>): boolean => {
  const identity = parts.filter(Boolean).join(' ').toLowerCase()
  return (
    identity.includes('maafw') &&
    (identity.includes('managed') ||
      identity.includes('托管') ||
      identity.includes('project_update') ||
      identity.includes('project-update'))
  )
}

export const isMaaFWManagedProvider = (provider: GameProviderItem): boolean =>
  isMaaFWManagedIdentity(provider.name, provider.displayName, provider.owner)

export const deriveEmulatorAdbPath = (config: EmulatorConfig | undefined): string | null => {
  const executablePath = config?.Info?.Path?.trim()
  if (!executablePath) return null
  const slashIndex = Math.max(executablePath.lastIndexOf('/'), executablePath.lastIndexOf('\\'))
  if (slashIndex < 0) return 'adb.exe'
  return `${executablePath.slice(0, slashIndex + 1)}adb.exe`
}

export const buildPresetLockedGamePayload = (
  current: GameConfig,
  patch: GameConfig,
  presets: GamePresetItem[],
  emulatorData: Record<string, EmulatorConfig>
): GameConfig => {
  const presetKey = patch.Info?.PresetKey ?? current.Info?.PresetKey
  const preset = presets.find(item => item.key === presetKey)
  if (!preset) throw new Error('游戏预设不可用，无法安全保存配置')

  const mergedData = { ...(current.Data || {}), ...(patch.Data || {}) }
  const isPresetChange = Boolean(current.Info?.PresetKey && current.Info.PresetKey !== preset.key)
  const patchDefinesInstallPath = Object.prototype.hasOwnProperty.call(
    patch.Data || {},
    'InstallPath'
  )
  const patchDefinesLaunchArgs = Object.prototype.hasOwnProperty.call(
    patch.Data || {},
    'LaunchArgs'
  )
  if (preset.platform === 'pc') {
    return {
      Info: {
        Name: preset.name,
        Platform: preset.platform,
        Provider: preset.provider,
        PresetKey: preset.key,
      },
      Data: {
        InstallPath:
          isPresetChange && !patchDefinesInstallPath ? null : mergedData.InstallPath || null,
        LaunchArgs:
          isPresetChange && !patchDefinesLaunchArgs ? null : mergedData.LaunchArgs || null,
        PackageName: null,
        EmulatorId: null,
        EmulatorIndex: null,
        AdbPath: null,
      },
    }
  }

  const emulatorId = mergedData.EmulatorId || null
  return {
    Info: {
      Name: preset.name,
      Platform: preset.platform,
      Provider: preset.provider,
      PresetKey: preset.key,
    },
    Data: {
      InstallPath: null,
      LaunchArgs: null,
      PackageName: preset.packageName || null,
      EmulatorId: emulatorId,
      EmulatorIndex: mergedData.EmulatorIndex || '0',
      AdbPath: emulatorId ? deriveEmulatorAdbPath(emulatorData[emulatorId]) : null,
    },
  }
}

export function useGameCenter() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const gameIndex = ref<GameConfigIndexItem[]>([])
  const gameData = ref<Record<string, GameConfig>>({})
  const providers = ref<GameProviderItem[]>([])
  const presets = ref<GamePresetItem[]>([])
  const emulatorIndex = ref<EmulatorConfigIndexItem[]>([])
  const emulatorData = ref<Record<string, EmulatorConfig>>({})
  const gameSignResponse = ref<GameSignAccountsListOut | null>(null)
  const gameSignLoading = ref(false)
  const actionStates = reactive<Record<string, GameActionState>>({})
  const taskStates = reactive<Record<string, GameTaskStatusOut>>({})
  const taskErrors = reactive<Record<string, string>>({})
  const emulatorDeviceOptions = reactive<Record<string, ComboBoxItem[]>>({})
  const emulatorDevicesLoading = reactive<Record<string, boolean>>({})

  const games = computed<ManagedGame[]>(() =>
    gameIndex.value
      .filter(item => Boolean(gameData.value[item.uid]))
      .map(item => ({ id: item.uid, config: gameData.value[item.uid] }))
  )
  const gameSignAccounts = computed<GameSignAccountSummary[]>(() => {
    const data = gameSignResponse.value?.data as any
    if (Array.isArray(data?.accounts)) return data.accounts
    if (Array.isArray(data)) return data

    const instances = Array.isArray(data?.instances) ? data.instances : []
    return instances
      .map((instance: any): GameSignAccountSummary | null => {
        const uid = String(instance?.uid || '').trim()
        if (!uid) return null
        const account = data?.[uid]?.GameSignAccount || data?.[uid] || {}
        const platforms = [
          account.MiyousheToken ? '米游社' : '',
          account.KuroToken ? '库街区' : '',
          account.SklandToken ? '森空岛' : '',
        ].filter(Boolean)
        return {
          uid,
          type: String(instance?.type || 'GameSignAccountGroup'),
          name: String(account.Name || '用户'),
          game: platforms.length > 0 ? platforms.join(' / ') : '未配置平台',
          enabled: account.Enabled ?? true,
        }
      })
      .filter((account: GameSignAccountSummary | null): account is GameSignAccountSummary =>
        Boolean(account)
      )
  })
  const emulatorOptions = computed(() =>
    emulatorIndex.value.map(item => ({
      label: emulatorData.value[item.uid]?.Info?.Name || item.uid,
      value: item.uid,
    }))
  )
  const availablePresets = computed(() =>
    presets.value.filter(preset => {
      const provider = providers.value.find(item => item.name === preset.provider)
      if (isMaaFWManagedIdentity(preset.provider, preset.name)) return false
      return provider ? !isMaaFWManagedProvider(provider) : true
    })
  )

  const stateFor = (gameId: string): GameActionState => {
    actionStates[gameId] ||= emptyActionState()
    return actionStates[gameId]
  }

  const taskFor = (gameId: string): GameTaskStatusOut | undefined => taskStates[gameId]
  const taskErrorFor = (gameId: string): string => taskErrors[gameId] || ''
  const expectedRevisionFor = (gameId: string): number => {
    const revision = gameData.value[gameId]?.Revision
    if (typeof revision !== 'number') throw new Error('游戏配置版本不可用，请刷新后重试')
    return revision
  }

  const applyTaskStatus = (gameId: string, task: GameTaskStatusOut): GameTaskStatusOut => {
    taskStates[gameId] = task
    stateFor(gameId).installing = task.running === true
    return task
  }

  const loadGames = async () => {
    const response = await Service.getGamesApiGameCenterGetPost({})
    if (response.code !== 200) throw responseError(response.message, '加载游戏列表失败')
    gameIndex.value = response.index || []
    gameData.value = response.data || {}
    for (const item of gameIndex.value) stateFor(item.uid)
  }

  const loadProviders = async () => {
    const response = await Service.listProvidersApiGameCenterProvidersPost()
    if (response.code !== 200) throw responseError(response.message, '加载游戏 provider 失败')
    providers.value = response.providers || []
  }

  const loadPresets = async () => {
    const response = await Service.listPresetsApiGameCenterPresetsPost()
    if (response.code !== 200) throw responseError(response.message, '加载游戏预设失败')
    presets.value = response.presets || []
  }

  const loadEmulators = async () => {
    const response = await Service.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    if (response.code !== 200) throw responseError(response.message, '加载模拟器列表失败')
    emulatorIndex.value = response.index || []
    emulatorData.value = response.data || {}
  }

  const loadGameSignAccounts = async () => {
    gameSignLoading.value = true
    try {
      const response = await Service.listGameSignAccountsApiToolsSignAccountListPost()
      if (response.code !== 200) throw responseError(response.message, '加载游戏签到账户失败')
      gameSignResponse.value = response
    } finally {
      gameSignLoading.value = false
    }
  }

  const loadEmulatorDevices = async (emulatorId: string): Promise<ComboBoxItem[]> => {
    if (!emulatorId) return []
    emulatorDevicesLoading[emulatorId] = true
    try {
      const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
        emulatorId,
      })
      if (response.code !== 200) {
        throw responseError(response.message, '加载模拟器实例失败')
      }
      emulatorDeviceOptions[emulatorId] = (response.data || []).filter(
        (item): item is ComboBoxItem & { value: string } => typeof item.value === 'string'
      )
      return emulatorDeviceOptions[emulatorId]
    } finally {
      emulatorDevicesLoading[emulatorId] = false
    }
  }

  const loadTaskStatus = async (gameId: string): Promise<GameTaskStatusOut> => {
    try {
      const response = await Service.taskStatusApiGameCenterTaskStatusPost({ gameId })
      if (response.code !== 200) throw responseError(response.message, '加载游戏任务状态失败')
      taskErrors[gameId] = ''
      return applyTaskStatus(gameId, response)
    } catch (cause) {
      taskErrors[gameId] = readableGameCenterError(cause, '加载游戏任务状态失败')
      throw cause
    }
  }

  const loadTaskStatuses = async (): Promise<void> => {
    const results = await Promise.allSettled(gameIndex.value.map(item => loadTaskStatus(item.uid)))
    const failure = results.find(
      (result): result is PromiseRejectedResult => result.status === 'rejected'
    )
    if (failure) throw failure.reason
  }

  const refresh = async () => {
    loading.value = true
    error.value = null
    try {
      const results = await Promise.allSettled([
        loadGames(),
        loadProviders(),
        loadPresets(),
        loadEmulators(),
        loadGameSignAccounts(),
      ])
      const failures = results.filter(
        (result): result is PromiseRejectedResult => result.status === 'rejected'
      )
      if (gameIndex.value.length > 0) {
        try {
          await loadTaskStatuses()
        } catch (cause) {
          failures.push({
            status: 'rejected',
            reason: cause,
          })
        }
      }
      if (failures.length > 0) {
        const messages = failures.map(item => readableGameCenterError(item.reason))
        error.value = [...new Set(messages)].join('；')
        logger.error(`加载游戏中心数据失败: ${error.value}`)
      }
    } finally {
      loading.value = false
    }
  }

  const addGame = async (preset: string): Promise<string> => {
    const selectedPreset = presets.value.find(item => item.key === preset)
    if (!selectedPreset) throw new Error('请选择有效的游戏预设')
    const defaultEmulatorId =
      selectedPreset.platform === 'emulator' ? (emulatorIndex.value[0]?.uid ?? null) : null
    const data = buildPresetLockedGamePayload(
      { Info: { PresetKey: preset }, Data: { EmulatorId: defaultEmulatorId } },
      {},
      presets.value,
      emulatorData.value
    )
    const response = await Service.addGameApiGameCenterAddPost({ preset, data })
    if (response.code !== 200 || !response.gameId)
      throw responseError(response.message, '添加游戏失败')
    await loadGames()
    return response.gameId
  }

  const updateGame = async (gameId: string, data: GameConfig): Promise<GameConfig> => {
    const game = gameData.value[gameId]
    if (!game) throw new Error('游戏配置已不存在')
    const state = stateFor(gameId)
    state.saving = true
    try {
      const sanitizedData = buildPresetLockedGamePayload(
        game,
        data,
        presets.value,
        emulatorData.value
      )
      const response = await Service.updateGameApiGameCenterUpdatePost({
        gameId,
        data: sanitizedData,
        expectedRevision: game.Revision ?? undefined,
      })
      if (response.code !== 200 || !response.data) {
        if (response.code === 409) await loadGames()
        throw responseError(response.message, '保存游戏配置失败')
      }
      gameData.value = { ...gameData.value, [gameId]: response.data }
      return response.data
    } finally {
      state.saving = false
    }
  }

  const deleteGame = async (gameId: string) => {
    const game = gameData.value[gameId]
    if (!game) return
    const state = stateFor(gameId)
    state.deleting = true
    try {
      const response = await Service.deleteGameApiGameCenterDeletePost({
        gameId,
        expectedRevision: game.Revision ?? undefined,
      })
      if (response.code !== 200) {
        if (response.code === 409) await loadGames()
        throw responseError(response.message, '删除游戏失败')
      }
      gameIndex.value = gameIndex.value.filter(item => item.uid !== gameId)
      const next = { ...gameData.value }
      delete next[gameId]
      gameData.value = next
    } finally {
      state.deleting = false
    }
  }

  const reorderGames = async (gameIds: string[]) => {
    const byId = new Map(gameIndex.value.map(item => [item.uid, item]))
    const reordered = gameIds.map(id => byId.get(id)).filter(Boolean) as GameConfigIndexItem[]
    if (reordered.length !== gameIndex.value.length) throw new Error('游戏排序必须包含全部游戏')

    const previous = [...gameIndex.value]
    gameIndex.value = reordered
    try {
      const response = await Service.reorderGamesApiGameCenterOrderPost({
        indexList: gameIds,
      })
      if (response.code !== 200) throw responseError(response.message, '游戏排序失败')
    } catch (cause) {
      gameIndex.value = previous
      try {
        await loadGames()
      } catch (reloadCause) {
        logger.error(
          `排序失败后刷新权威顺序失败: ${
            reloadCause instanceof Error ? reloadCause.message : String(reloadCause)
          }`
        )
      }
      throw cause
    }
  }

  const checkGame = async (gameId: string): Promise<GameCheckOut> => {
    const state = stateFor(gameId)
    state.checking = true
    try {
      const response = await Service.checkGameApiGameCenterCheckPost({
        gameId,
        expectedRevision: expectedRevisionFor(gameId),
      })
      if (response.code !== 200) throw responseError(response.message, '检查游戏失败')
      // check 会原子更新 Cache 并推进 Revision；重新读取以免后续 CAS 使用旧版本。
      await loadGames()
      return response
    } finally {
      state.checking = false
    }
  }

  const launchGame = async (gameId: string) => {
    const state = stateFor(gameId)
    state.launching = true
    try {
      const response = await Service.launchGameApiGameCenterLaunchPost({
        gameId,
        expectedRevision: expectedRevisionFor(gameId),
      })
      if (response.code !== 200) throw responseError(response.message, '启动游戏失败')
      return response.provider || ''
    } finally {
      state.launching = false
    }
  }

  const closeGame = async (gameId: string) => {
    const state = stateFor(gameId)
    state.closing = true
    try {
      const response = await Service.closeGameApiGameCenterClosePost({
        gameId,
        expectedRevision: expectedRevisionFor(gameId),
      })
      if (response.code !== 200) throw responseError(response.message, '关闭游戏失败')
      return response.provider || ''
    } finally {
      state.closing = false
    }
  }

  const installOrUpdateGame = async (gameId: string): Promise<GameTaskStatusOut> => {
    const state = stateFor(gameId)
    state.installing = true
    try {
      const response = await Service.installGameApiGameCenterInstallPost({
        gameId,
        expectedRevision: expectedRevisionFor(gameId),
      })
      if (response.code !== 200 || response.taskStatus !== 'running') {
        throw responseError(response.message, '启动安装或更新任务失败')
      }
      return applyTaskStatus(gameId, response)
    } catch (cause) {
      state.installing = false
      throw cause
    }
  }

  const cancelGameTask = async (gameId: string): Promise<GameTaskStatusOut> => {
    const state = stateFor(gameId)
    const expectedTaskId = taskFor(gameId)?.taskId
    if (!expectedTaskId) throw new Error('任务标识不可用，请刷新任务状态后重试')
    state.canceling = true
    try {
      const response = await Service.cancelGameApiGameCenterCancelPost({
        gameId,
        expectedRevision: expectedRevisionFor(gameId),
        expectedTaskId,
      })
      if (response.code !== 200 || response.taskStatus !== 'cancelled') {
        throw responseError(response.message, '取消游戏任务失败')
      }
      return applyTaskStatus(gameId, response)
    } finally {
      state.canceling = false
    }
  }

  const providerFor = (name: string | null | undefined) =>
    providers.value.find(provider => provider.name === name)

  return {
    loading,
    error,
    gameIndex,
    gameData,
    providers,
    presets,
    emulatorIndex,
    emulatorData,
    emulatorOptions,
    emulatorDeviceOptions,
    emulatorDevicesLoading,
    availablePresets,
    gameSignResponse,
    gameSignLoading,
    gameSignAccounts,
    actionStates,
    taskStates,
    games,
    stateFor,
    taskFor,
    taskErrorFor,
    providerFor,
    refresh,
    loadGames,
    loadProviders,
    loadPresets,
    loadEmulators,
    loadGameSignAccounts,
    loadEmulatorDevices,
    loadTaskStatus,
    loadTaskStatuses,
    addGame,
    updateGame,
    deleteGame,
    reorderGames,
    checkGame,
    launchGame,
    closeGame,
    installOrUpdateGame,
    cancelGameTask,
  }
}
