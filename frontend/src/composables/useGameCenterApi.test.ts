import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { GamePresetItem } from '@/api'

const PC_PLATFORM = 'pc' as GamePresetItem['platform']
const EMULATOR_PLATFORM = 'emulator' as GamePresetItem['platform']

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }
const service = vi.hoisted(() => ({
  getGamesApiGameCenterGetPost: vi.fn(),
  listProvidersApiGameCenterProvidersPost: vi.fn(),
  listPresetsApiGameCenterPresetsPost: vi.fn(),
  getEmulatorApiEmulatorGetPost: vi.fn(),
  getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost: vi.fn(),
  listGameSignAccountsApiToolsSignAccountListPost: vi.fn(),
  addGameApiGameCenterAddPost: vi.fn(),
  updateGameApiGameCenterUpdatePost: vi.fn(),
  deleteGameApiGameCenterDeletePost: vi.fn(),
  reorderGamesApiGameCenterOrderPost: vi.fn(),
  checkGameApiGameCenterCheckPost: vi.fn(),
  launchGameApiGameCenterLaunchPost: vi.fn(),
  closeGameApiGameCenterClosePost: vi.fn(),
  installGameApiGameCenterInstallPost: vi.fn(),
  cancelGameApiGameCenterCancelPost: vi.fn(),
  taskStatusApiGameCenterTaskStatusPost: vi.fn(),
}))

vi.mock('@/api', () => ({ Service: service }))

const gameResponse = (revision = 3, name = '星穹铁道') => ({
  code: 200,
  index: [{ uid: 'game-a', type: 'GameConfig' }],
  data: {
    'game-a': {
      Info: {
        Name: name,
        Platform: 'pc',
        Provider: 'mihoyo_pc',
        PresetKey: 'starrail_cn',
      },
      Data: { InstallPath: 'D:/Games/StarRail' },
      Cache: { Installed: true, LocalVersion: '3.4.0' },
      Revision: revision,
    },
  },
})

const loadComposable = async () => {
  vi.resetModules()
  return await import('./useGameCenterApi')
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => logger },
  })
  service.getGamesApiGameCenterGetPost.mockResolvedValue(gameResponse())
  service.listProvidersApiGameCenterProvidersPost.mockResolvedValue({
    code: 200,
    providers: [
      {
        name: 'mihoyo_pc',
        displayName: '米哈游 PC',
        platforms: ['pc'],
        capabilities: ['check', 'launch', 'close'],
        owner: 'host',
      },
    ],
  })
  service.listPresetsApiGameCenterPresetsPost.mockResolvedValue({
    code: 200,
    presets: [
      {
        key: 'starrail_cn',
        name: '星穹铁道',
        platform: PC_PLATFORM,
        provider: 'mihoyo_pc',
      },
    ],
  })
  service.getEmulatorApiEmulatorGetPost.mockResolvedValue({
    code: 200,
    index: [],
    data: {},
  })
  service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost.mockResolvedValue({
    code: 200,
    data: [{ label: '实例 0', value: '0' }],
  })
  service.listGameSignAccountsApiToolsSignAccountListPost.mockResolvedValue({
    code: 200,
    data: { accounts: [] },
  })
  service.taskStatusApiGameCenterTaskStatusPost.mockResolvedValue({
    code: 200,
    running: false,
    gameId: 'game-a',
    taskStatus: null,
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useGameCenterApi 正式生产链', () => {
  it('并行加载持久化游戏、provider、预设和模拟器', async () => {
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()

    await center.refresh()

    expect(center.games.value).toHaveLength(1)
    expect(center.games.value[0].config.Revision).toBe(3)
    expect(center.providerFor('mihoyo_pc')?.displayName).toBe('米哈游 PC')
    expect(center.presets.value[0].key).toBe('starrail_cn')
    expect(center.error.value).toBeNull()
  })

  it('按正式 Config 响应结构展示非空游戏签到账户', async () => {
    service.listGameSignAccountsApiToolsSignAccountListPost.mockResolvedValue({
      code: 200,
      data: {
        instances: [{ uid: 'account-a', type: 'GameSignAccountGroup' }],
        'account-a': {
          GameSignAccount: {
            Name: '主账号',
            Enabled: true,
            MiyousheToken: 'stored-token',
            KuroToken: '',
            SklandToken: 'stored-token',
          },
        },
      },
    })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()

    await center.loadGameSignAccounts()

    expect(center.gameSignAccounts.value).toEqual([
      {
        uid: 'account-a',
        type: 'GameSignAccountGroup',
        name: '主账号',
        game: '米游社 / 森空岛',
        enabled: true,
      },
    ])
    expect(JSON.stringify(center.gameSignAccounts.value)).not.toContain('stored-token')
  })

  it('新增游戏把 preset 锁定字段写入正式创建 payload', async () => {
    service.addGameApiGameCenterAddPost.mockResolvedValue({
      code: 200,
      gameId: 'game-new',
      data: gameResponse().data['game-a'],
    })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    await Promise.all([center.loadPresets(), center.loadEmulators()])

    await center.addGame('starrail_cn')

    expect(service.addGameApiGameCenterAddPost).toHaveBeenCalledWith({
      preset: 'starrail_cn',
      data: {
        Info: {
          Name: '星穹铁道',
          Platform: 'pc',
          Provider: 'mihoyo_pc',
          PresetKey: 'starrail_cn',
        },
        Data: {
          InstallPath: null,
          LaunchArgs: null,
          PackageName: null,
          EmulatorId: null,
          EmulatorIndex: null,
          AdbPath: null,
        },
      },
    })
  })

  it('可选预设隐藏 MaaFW 托管 provider，但保留底层 provider 数据', async () => {
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    center.providers.value = [
      {
        name: 'maafw_managed',
        displayName: 'MaaFW 托管项目',
        platforms: ['pc'],
        capabilities: ['check'],
        owner: 'automas_maafw_runner',
      },
      {
        name: 'mihoyo_pc',
        displayName: '米哈游 PC',
        platforms: ['pc'],
        capabilities: ['check'],
        owner: 'host',
      },
      {
        name: 'maafw_runner',
        displayName: 'MaaFW 项目运行器',
        platforms: ['pc'],
        capabilities: ['check', 'launch', 'close'],
        owner: 'automas_maafw_runner',
      },
      {
        name: 'maafw_project',
        displayName: 'MaaFW 项目',
        platforms: ['pc'],
        capabilities: ['check'],
        owner: 'automas_maafw_project_update',
      },
    ]
    center.presets.value = [
      {
        key: 'maafw-project',
        name: 'MaaFW 项目',
        platform: PC_PLATFORM,
        provider: 'maafw_managed',
      },
      {
        key: 'starrail_cn',
        name: '星穹铁道',
        platform: PC_PLATFORM,
        provider: 'mihoyo_pc',
      },
      {
        key: 'maafw-runner',
        name: '普通 MaaFW 项目',
        platform: PC_PLATFORM,
        provider: 'maafw_runner',
      },
      {
        key: 'maafw-cn-managed',
        name: 'MaaFW 托管项目（中文标记）',
        platform: PC_PLATFORM,
        provider: 'maafw_project',
      },
    ]

    expect(center.availablePresets.value.map(item => item.key)).toEqual([
      'starrail_cn',
      'maafw-runner',
    ])
    expect(center.providers.value).toHaveLength(4)
  })

  it('保存始终携带 expectedRevision 并采用后端返回的新 revision', async () => {
    service.updateGameApiGameCenterUpdatePost.mockResolvedValue({
      code: 200,
      gameId: 'game-a',
      data: gameResponse(4, '新名称').data['game-a'],
    })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    await Promise.all([center.loadGames(), center.loadPresets(), center.loadEmulators()])

    const updated = await center.updateGame('game-a', {
      Info: { Name: '新名称' },
    })

    expect(service.updateGameApiGameCenterUpdatePost).toHaveBeenCalledWith({
      gameId: 'game-a',
      data: {
        Info: {
          Name: '星穹铁道',
          Platform: 'pc',
          Provider: 'mihoyo_pc',
          PresetKey: 'starrail_cn',
        },
        Data: {
          InstallPath: 'D:/Games/StarRail',
          LaunchArgs: null,
          PackageName: null,
          EmulatorId: null,
          EmulatorIndex: null,
          AdbPath: null,
        },
      },
      expectedRevision: 3,
    })
    expect(updated.Revision).toBe(4)
    expect(center.gameData.value['game-a'].Info?.Name).toBe('新名称')
    expect(center.stateFor('game-a').saving).toBe(false)
  })

  it('CAS 冲突会刷新权威状态并拒绝本地假成功', async () => {
    service.updateGameApiGameCenterUpdatePost.mockResolvedValue({
      code: 409,
      status: 'error',
      message: '游戏配置已更新',
    })
    service.getGamesApiGameCenterGetPost
      .mockResolvedValueOnce(gameResponse())
      .mockResolvedValueOnce(gameResponse(9, '其他窗口的新值'))
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    await Promise.all([center.loadGames(), center.loadPresets(), center.loadEmulators()])

    await expect(center.updateGame('game-a', { Info: { Name: '过期写入' } })).rejects.toThrow(
      '已更新'
    )
    expect(center.gameData.value['game-a'].Revision).toBe(9)
    expect(center.gameData.value['game-a'].Info?.Name).toBe('其他窗口的新值')
  })

  it('检查后重新读取被后端推进的 cache revision', async () => {
    service.checkGameApiGameCenterCheckPost.mockResolvedValue({
      code: 200,
      installed: true,
      local_version: '3.4.0',
      latest_version: '3.4.0',
      needs_update: false,
    })
    service.getGamesApiGameCenterGetPost
      .mockResolvedValueOnce(gameResponse(3))
      .mockResolvedValueOnce(gameResponse(4))
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    await center.loadGames()

    const result = await center.checkGame('game-a')

    expect(result.installed).toBe(true)
    expect(service.checkGameApiGameCenterCheckPost).toHaveBeenCalledWith({
      gameId: 'game-a',
      expectedRevision: 3,
    })
    expect(center.gameData.value['game-a'].Revision).toBe(4)
    expect(center.stateFor('game-a').checking).toBe(false)
  })

  it('预设锁定 payload 会覆盖旧 provider/平台并清理跨平台残留字段', async () => {
    const { buildPresetLockedGamePayload } = await loadComposable()
    const payload = buildPresetLockedGamePayload(
      {
        Info: {
          Name: '被修改的名字',
          Platform: 'emulator',
          Provider: 'evil_provider',
          PresetKey: 'starrail_cn',
        },
        Data: {
          InstallPath: 'D:/Games/StarRail',
          PackageName: 'evil.package',
          EmulatorId: 'emu-old',
          EmulatorIndex: '9',
          AdbPath: 'D:/bad/adb.exe',
        },
      },
      { Info: { Provider: 'still_evil' }, Data: { LaunchArgs: '--windowed' } },
      [
        {
          key: 'starrail_cn',
          name: '星穹铁道',
          platform: PC_PLATFORM,
          provider: 'mihoyo_pc',
        },
      ],
      {}
    )

    expect(payload).toEqual({
      Info: {
        Name: '星穹铁道',
        Platform: 'pc',
        Provider: 'mihoyo_pc',
        PresetKey: 'starrail_cn',
      },
      Data: {
        InstallPath: 'D:/Games/StarRail',
        LaunchArgs: '--windowed',
        PackageName: null,
        EmulatorId: null,
        EmulatorIndex: null,
        AdbPath: null,
      },
    })
  })

  it('模拟器预设锁定包名并从所选模拟器配置派生 ADB 路径', async () => {
    const { buildPresetLockedGamePayload } = await loadComposable()
    const payload = buildPresetLockedGamePayload(
      {
        Info: { PresetKey: 'arknights_android_cn' },
        Data: { EmulatorId: 'emu-a', EmulatorIndex: '2', AdbPath: 'C:/stale/adb.exe' },
      },
      { Data: { PackageName: 'evil.package' } },
      [
        {
          key: 'arknights_android_cn',
          name: '明日方舟（模拟器国服）',
          platform: EMULATOR_PLATFORM,
          provider: 'adb_apk',
          packageName: 'com.hypergryph.arknights',
        },
      ],
      {
        'emu-a': {
          Info: {
            Name: '雷电',
            Type: 'ldplayer',
            Path: 'C:\\LDPlayer\\LDPlayer9\\ldconsole.exe',
          },
        },
      }
    )

    expect(payload.Info).toMatchObject({
      Platform: 'emulator',
      Provider: 'adb_apk',
      PresetKey: 'arknights_android_cn',
    })
    expect(payload.Data).toEqual({
      InstallPath: null,
      LaunchArgs: null,
      PackageName: 'com.hypergryph.arknights',
      EmulatorId: 'emu-a',
      EmulatorIndex: '2',
      AdbPath: 'C:\\LDPlayer\\LDPlayer9\\adb.exe',
    })
  })

  it('切换 PC 游戏预设时不会沿用上一款游戏的路径和启动参数', async () => {
    const { buildPresetLockedGamePayload } = await loadComposable()
    const payload = buildPresetLockedGamePayload(
      {
        Info: { PresetKey: 'starrail_cn' },
        Data: {
          InstallPath: 'D:/Games/StarRail',
          LaunchArgs: '--old-game-argument',
        },
      },
      { Info: { PresetKey: 'genshin_cn' } },
      [
        {
          key: 'genshin_cn',
          name: '原神（国服）',
          platform: PC_PLATFORM,
          provider: 'mihoyo_pc',
        },
      ],
      {}
    )

    expect(payload).toMatchObject({
      Info: {
        Name: '原神（国服）',
        PresetKey: 'genshin_cn',
      },
      Data: {
        InstallPath: null,
        LaunchArgs: null,
      },
    })
  })

  it('模拟器实例下拉使用正式 combobox 接口', async () => {
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()

    const options = await center.loadEmulatorDevices('emu-a')

    expect(service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost).toHaveBeenCalledWith({
      emulatorId: 'emu-a',
    })
    expect(options).toEqual([{ label: '实例 0', value: '0' }])
    expect(center.emulatorDevicesLoading['emu-a']).toBe(false)
  })

  it('启动失败向上传播且不会留下 loading 状态', async () => {
    service.launchGameApiGameCenterLaunchPost.mockResolvedValue({
      code: 503,
      status: 'error',
      message: 'provider 当前不可用',
    })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    await center.loadGames()

    await expect(center.launchGame('game-a')).rejects.toThrow('provider 当前不可用')
    expect(service.launchGameApiGameCenterLaunchPost).toHaveBeenCalledWith({
      gameId: 'game-a',
      expectedRevision: 3,
    })
    expect(center.stateFor('game-a').launching).toBe(false)
  })

  it('页面刷新会恢复后端仍在运行的安装任务进度', async () => {
    service.taskStatusApiGameCenterTaskStatusPost.mockResolvedValue({
      code: 200,
      running: true,
      taskId: 'task-a',
      gameId: 'game-a',
      taskStatus: 'running',
      phase: 'download',
      percent: 37,
      downloaded: 37,
      total: 100,
      speed: 12,
      detail: '下载中',
    })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()

    await center.refresh()

    expect(service.taskStatusApiGameCenterTaskStatusPost).toHaveBeenCalledWith({
      gameId: 'game-a',
    })
    expect(center.taskFor('game-a')).toMatchObject({
      running: true,
      phase: 'download',
      percent: 37,
    })
    expect(center.stateFor('game-a').installing).toBe(true)
  })

  it('安装与取消携带配置 revision 和当前 taskId', async () => {
    service.installGameApiGameCenterInstallPost.mockResolvedValue({
      code: 200,
      running: true,
      taskId: 'task-current',
      gameId: 'game-a',
      taskStatus: 'running',
      phase: 'queued',
    })
    service.cancelGameApiGameCenterCancelPost.mockResolvedValue({
      code: 200,
      running: false,
      taskId: 'task-current',
      gameId: 'game-a',
      taskStatus: 'cancelled',
      phase: 'cancelled',
    })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    await center.loadGames()

    await center.installOrUpdateGame('game-a')
    expect(service.installGameApiGameCenterInstallPost).toHaveBeenCalledWith({
      gameId: 'game-a',
      expectedRevision: 3,
    })

    await center.cancelGameTask('game-a')
    expect(service.cancelGameApiGameCenterCancelPost).toHaveBeenCalledWith({
      gameId: 'game-a',
      expectedRevision: 3,
      expectedTaskId: 'task-current',
    })
  })

  it('安装和取消必须收到真实任务终态，拒绝 code 200 假成功', async () => {
    service.installGameApiGameCenterInstallPost.mockResolvedValue({
      code: 200,
      running: false,
      gameId: 'game-a',
      taskStatus: 'failed',
      message: '官方启动器不可用',
    })
    service.cancelGameApiGameCenterCancelPost.mockResolvedValue({
      code: 409,
      status: 'error',
      message: '没有可取消的运行任务',
      gameId: 'game-a',
    })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    await center.loadGames()

    await expect(center.installOrUpdateGame('game-a')).rejects.toThrow('官方启动器不可用')
    expect(center.stateFor('game-a').installing).toBe(false)
    service.taskStatusApiGameCenterTaskStatusPost.mockResolvedValue({
      code: 200,
      running: true,
      taskId: 'task-current',
      gameId: 'game-a',
      taskStatus: 'running',
      phase: 'download',
    })
    await center.loadTaskStatus('game-a')
    await expect(center.cancelGameTask('game-a')).rejects.toThrow('没有可取消')
    expect(service.cancelGameApiGameCenterCancelPost).toHaveBeenCalledWith({
      gameId: 'game-a',
      expectedRevision: 3,
      expectedTaskId: 'task-current',
    })
    expect(center.stateFor('game-a').canceling).toBe(false)
  })

  it('任务轮询失败会暴露错误，手动重试成功后清除', async () => {
    service.taskStatusApiGameCenterTaskStatusPost
      .mockRejectedValueOnce(new Error('后端暂时不可达'))
      .mockResolvedValueOnce({
        code: 200,
        running: false,
        taskId: 'task-a',
        gameId: 'game-a',
        taskStatus: 'handed_off',
        phase: 'awaiting_user',
        detail: '已交给官方启动器',
      })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()

    await expect(center.loadTaskStatus('game-a')).rejects.toThrow('后端暂时不可达')
    expect(center.taskErrorFor('game-a')).toBe('后端暂时不可达')

    const retried = await center.loadTaskStatus('game-a')
    expect(retried.taskStatus).toBe('handed_off')
    expect(center.taskErrorFor('game-a')).toBe('')
  })

  it('排序失败后重新读取权威顺序，不保留本地假成功', async () => {
    service.getGamesApiGameCenterGetPost
      .mockResolvedValueOnce({
        code: 200,
        index: [
          { uid: 'game-a', type: 'GameConfig' },
          { uid: 'game-b', type: 'GameConfig' },
        ],
        data: {
          'game-a': gameResponse().data['game-a'],
          'game-b': {
            ...gameResponse().data['game-a'],
            Info: { ...gameResponse().data['game-a'].Info, Name: '第二个游戏' },
          },
        },
      })
      .mockResolvedValueOnce({
        code: 200,
        index: [
          { uid: 'game-a', type: 'GameConfig' },
          { uid: 'game-b', type: 'GameConfig' },
        ],
        data: {
          'game-a': gameResponse().data['game-a'],
          'game-b': {
            ...gameResponse().data['game-a'],
            Info: { ...gameResponse().data['game-a'].Info, Name: '第二个游戏' },
          },
        },
      })
    service.reorderGamesApiGameCenterOrderPost.mockResolvedValue({
      code: 409,
      status: 'error',
      message: '顺序已变化',
    })
    const { useGameCenter } = await loadComposable()
    const center = useGameCenter()
    await center.loadGames()

    await expect(center.reorderGames(['game-b', 'game-a'])).rejects.toThrow('顺序已变化')

    expect(center.gameIndex.value.map(item => item.uid)).toEqual(['game-a', 'game-b'])
    expect(service.getGamesApiGameCenterGetPost).toHaveBeenCalledTimes(2)
  })
})
