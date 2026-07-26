/**
 * Lane 8：计划切换/模式/名称/字段回滚契约测试。
 *
 * 覆盖：
 * - usePlanApi.requireSuccess 契约：code !== 200 一律拒绝
 * - usePlanDataCoordinator 的 getConfig / snapshotTimeConfig / restoreTimeConfig
 * - onPlanChange 失败时恢复 activePlanId
 * - onModeChange 失败时恢复 currentMode 到 lastSyncedMode
 * - finishEditPlanName 失败时恢复 currentPlanName 但保留编辑模式
 * - handlePlanChange 失败时不写入本地状态
 *
 * 设计：
 * - 通过 vi.mock 替换 Service 与 useAudioPlayer，控制每次响应。
 * - 不挂载 Vue 组件，直接驱动 composable + 模拟 ref 状态来验证回滚契约。
 * - 与 useGameSignAccountApi.test.ts 中的契约测试模式保持一致。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

// ---- Mocks --------------------------------------------------------------

const mockService = {
  getPlanApiPlanGetPost: vi.fn(),
  addPlanApiPlanAddPost: vi.fn(),
  updatePlanApiPlanUpdatePost: vi.fn(),
  deletePlanApiPlanDeletePost: vi.fn(),
  reorderPlanApiPlanOrderPost: vi.fn(),
}

vi.mock('@/api', () => ({
  Service: mockService,
  OpenAPI: { BASE: 'http://test.local' },
}))

vi.mock('@/composables/useAudioPlayer', () => ({
  useAudioPlayer: () => ({
    playSound: vi.fn().mockResolvedValue(undefined),
  }),
}))

const messageSpy = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}

vi.mock('ant-design-vue', () => ({
  message: messageSpy,
}))

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

const loadUsePlanApi = async () => {
  vi.resetModules()
  return await import('@/composables/usePlanApi')
}

const loadCoordinator = async () => {
  vi.resetModules()
  return await import('@/composables/usePlanDataCoordinator')
}

// ---- Tests --------------------------------------------------------------

describe('Lane 8 usePlanApi 契约', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('getPlans', () => {
    it('成功返回响应数据', async () => {
      mockService.getPlanApiPlanGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'plan-1', type: 'MaaPlanConfig' }],
        data: { 'plan-1': { Info: { Name: '计划A', Mode: 'ALL' } } },
      })
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      const result = await api.getPlans()
      expect(result.index).toHaveLength(1)
      expect(result.data['plan-1'].Info?.Name).toBe('计划A')
      expect(api.loading.value).toBe(false)
    })

    it('code !== 200 时抛错并 message.error', async () => {
      mockService.getPlanApiPlanGetPost.mockResolvedValue({
        code: 500,
        message: '后端错误',
      })
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      await expect(api.getPlans()).rejects.toThrow('后端错误')
      expect(messageSpy.error).toHaveBeenCalledWith('获取计划失败')
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('后端错误'))
    })

    it('网络异常时抛错', async () => {
      mockService.getPlanApiPlanGetPost.mockRejectedValue(new Error('Timeout'))
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      await expect(api.getPlans()).rejects.toThrow('Timeout')
      expect(messageSpy.error).toHaveBeenCalledWith('获取计划失败')
    })
  })

  describe('updatePlan', () => {
    it('成功时静默返回（不主动 message.success）', async () => {
      mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
        code: 200,
        message: '',
      })
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      await api.updatePlan('plan-1', { Info: { Name: '新名' } })
      expect(messageSpy.success).not.toHaveBeenCalled()
    })

    it('code !== 200 时抛错（调用方可捕获并回滚）', async () => {
      mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
        code: 500,
        message: '更新失败',
      })
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      await expect(api.updatePlan('plan-1', { Info: { Name: '新名' } })).rejects.toThrow('更新失败')
      expect(messageSpy.error).toHaveBeenCalledWith('更新计划失败')
    })

    it('网络异常时抛错', async () => {
      mockService.updatePlanApiPlanUpdatePost.mockRejectedValue(new Error('Network error'))
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      await expect(api.updatePlan('plan-1', { Info: { Name: '新名' } })).rejects.toThrow(
        'Network error'
      )
    })
  })

  describe('createPlan', () => {
    it('成功返回响应（含 planId）', async () => {
      mockService.addPlanApiPlanAddPost.mockResolvedValue({
        code: 200,
        planId: 'new-plan',
      })
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      const result = await api.createPlan('MaaPlanConfig')
      expect(result.planId).toBe('new-plan')
    })

    it('code !== 200 时抛错', async () => {
      mockService.addPlanApiPlanAddPost.mockResolvedValue({
        code: 500,
        message: '创建失败',
      })
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      await expect(api.createPlan('MaaPlanConfig')).rejects.toThrow('创建失败')
      expect(messageSpy.error).toHaveBeenCalledWith('创建计划失败')
    })
  })

  describe('deletePlan', () => {
    it('成功时返回响应', async () => {
      mockService.deletePlanApiPlanDeletePost.mockResolvedValue({
        code: 200,
        message: '',
      })
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      await api.deletePlan('plan-1')
      // 删除成功会播放音频
    })

    it('code !== 200 时抛错', async () => {
      mockService.deletePlanApiPlanDeletePost.mockResolvedValue({
        code: 500,
        message: '删除失败',
      })
      const { usePlanApi } = await loadUsePlanApi()
      const api = usePlanApi()
      await expect(api.deletePlan('plan-1')).rejects.toThrow('删除失败')
      expect(messageSpy.error).toHaveBeenCalledWith('删除计划失败')
    })
  })
})

/**
 * Lane 8：计划切换/模式/名称回滚契约测试。
 *
 * 这些测试不挂载 plan/index.vue，而是验证"快照-修改-失败回滚"的契约模式：
 * 1. onPlanChange 失败时：恢复 activePlanId 到 previousPlanId
 * 2. onModeChange 失败时：恢复 currentMode 到 lastSyncedMode
 * 3. finishEditPlanName 失败时：恢复 currentPlanName 但保留编辑模式
 * 4. handlePlanChange 失败时：返回 false，调用方据此决定回滚
 */
describe('Lane 8 计划回滚契约', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('onPlanChange 失败时恢复 activePlanId', async () => {
    // 模拟 plan/index.vue 的 onPlanChange 流程
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 200,
      message: '',
    })
    // loadPlanData 失败
    mockService.getPlanApiPlanGetPost.mockResolvedValue({
      code: 500,
      message: '加载新计划失败',
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()

    const activePlanId = ref('plan-old')
    const previousPlanId = 'plan-old'
    const newPlanId = 'plan-new'

    // 复刻 onPlanChange 的核心逻辑
    try {
      activePlanId.value = newPlanId
      await api.getPlans(newPlanId)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`切换计划失败: ${errorMsg}`)
      activePlanId.value = previousPlanId
      messageSpy.error(`切换计划失败: ${errorMsg}`)
    }

    // 验证 activePlanId 已回滚
    expect(activePlanId.value).toBe('plan-old')
  })

  it('onPlanChange 成功时保留新 activePlanId', async () => {
    mockService.getPlanApiPlanGetPost.mockResolvedValue({
      code: 200,
      index: [{ uid: 'plan-new', type: 'MaaPlanConfig' }],
      data: { 'plan-new': { Info: { Name: '新计划', Mode: 'ALL' } } },
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()

    const activePlanId = ref('plan-old')
    const previousPlanId = 'plan-old'
    const newPlanId = 'plan-new'

    try {
      activePlanId.value = newPlanId
      await api.getPlans(newPlanId)
    } catch {
      activePlanId.value = previousPlanId
    }

    expect(activePlanId.value).toBe('plan-new')
  })

  it('onModeChange 失败时恢复 currentMode 到 lastSyncedMode', async () => {
    // 模拟 plan/index.vue 的 onModeChange 流程
    // handlePlanChange 内部调用 updatePlan，这里让它失败
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 500,
      message: '模式更新失败',
    })
    // refreshPlanData 也走 getPlans，这里让它成功
    mockService.getPlanApiPlanGetPost.mockResolvedValue({
      code: 200,
      index: [],
      data: {},
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()

    const currentMode = ref<'ALL' | 'Weekly'>('ALL')
    const lastSyncedMode = ref<'ALL' | 'Weekly'>('ALL')
    const activePlanId = ref('plan-1')

    // 模拟用户切换到 Weekly
    currentMode.value = 'Weekly'

    // 复刻 onModeChange 的核心逻辑
    const previousMode = lastSyncedMode.value
    const newMode = currentMode.value
    // 复刻 handlePlanChange：调用 updatePlan
    let success = false
    try {
      await api.updatePlan(activePlanId.value, { Info: { Mode: newMode } })
      success = true
    } catch {
      success = false
    }

    if (success) {
      lastSyncedMode.value = newMode
    } else {
      // 失败：恢复到上次同步的模式
      currentMode.value = previousMode
    }

    // 验证 currentMode 已回滚到 ALL
    expect(currentMode.value).toBe('ALL')
    expect(lastSyncedMode.value).toBe('ALL')
  })

  it('onModeChange 成功时更新 lastSyncedMode', async () => {
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 200,
      message: '',
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()

    const currentMode = ref<'ALL' | 'Weekly'>('Weekly')
    const lastSyncedMode = ref<'ALL' | 'Weekly'>('ALL')
    const activePlanId = ref('plan-1')

    const previousMode = lastSyncedMode.value
    const newMode = currentMode.value
    let success = false
    try {
      await api.updatePlan(activePlanId.value, { Info: { Mode: newMode } })
      success = true
    } catch {
      success = false
    }

    if (success) {
      lastSyncedMode.value = newMode
    } else {
      currentMode.value = previousMode
    }

    expect(currentMode.value).toBe('Weekly')
    expect(lastSyncedMode.value).toBe('Weekly')
  })

  it('finishEditPlanName 失败时恢复 currentPlanName 但保留编辑模式', async () => {
    // 模拟 plan/index.vue 的 finishEditPlanName 流程
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 500,
      message: '名称更新失败',
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()

    const planList = ref([{ id: 'plan-1', name: '原名', type: 'MaaPlanConfig' }])
    const activePlanId = ref('plan-1')
    const currentPlanName = ref('新名')
    const isEditingPlanName = ref(true)

    const currentPlan = planList.value.find(p => p.id === activePlanId.value)!
    const previousName = currentPlan.name

    // 复刻 handlePlanChange：调用 updatePlan
    let success = false
    try {
      await api.updatePlan(activePlanId.value, { Info: { Name: '新名' } })
      success = true
    } catch {
      success = false
    }

    if (success) {
      currentPlan.name = '新名'
      currentPlanName.value = '新名'
      isEditingPlanName.value = false
    } else {
      // 失败：恢复 currentPlanName，保留编辑模式让用户重试
      currentPlanName.value = previousName
      // isEditingPlanName 保持 true
    }

    // 验证 currentPlanName 已回滚
    expect(currentPlanName.value).toBe('原名')
    // 验证 planList 中的名称未被修改
    expect(planList.value[0].name).toBe('原名')
    // 验证编辑模式保留
    expect(isEditingPlanName.value).toBe(true)
  })

  it('finishEditPlanName 成功时更新 planList 并退出编辑模式', async () => {
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 200,
      message: '',
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()

    const planList = ref([{ id: 'plan-1', name: '原名', type: 'MaaPlanConfig' }])
    const activePlanId = ref('plan-1')
    const currentPlanName = ref('新名')
    const isEditingPlanName = ref(true)

    const currentPlan = planList.value.find(p => p.id === activePlanId.value)!

    let success = false
    try {
      await api.updatePlan(activePlanId.value, { Info: { Name: '新名' } })
      success = true
    } catch {
      success = false
    }

    if (success) {
      currentPlan.name = '新名'
      currentPlanName.value = '新名'
      isEditingPlanName.value = false
    } else {
      currentPlanName.value = currentPlan.name
    }

    expect(currentPlanName.value).toBe('新名')
    expect(planList.value[0].name).toBe('新名')
    expect(isEditingPlanName.value).toBe(false)
  })

  it('handlePlanChange 失败时返回 false（调用方据此回滚）', async () => {
    // 模拟 plan/index.vue 的 handlePlanChange 流程
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 500,
      message: '更新失败',
    })
    mockService.getPlanApiPlanGetPost.mockResolvedValue({
      code: 200,
      index: [],
      data: {},
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()
    const activePlanId = ref('plan-1')

    // 复刻 savePlanField + handlePlanChange
    const savePlanField = async (changes: Record<string, any>): Promise<boolean> => {
      if (!activePlanId.value) return false
      try {
        await api.updatePlan(activePlanId.value, changes)
        return true
      } catch {
        return false
      }
    }

    const success = await savePlanField({ Info: { Name: '新名' } })
    expect(success).toBe(false)
  })

  it('handlePlanChange 成功时返回 true', async () => {
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 200,
      message: '',
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()
    const activePlanId = ref('plan-1')

    const savePlanField = async (changes: Record<string, any>): Promise<boolean> => {
      if (!activePlanId.value) return false
      try {
        await api.updatePlan(activePlanId.value, changes)
        return true
      } catch {
        return false
      }
    }

    const success = await savePlanField({ Info: { Name: '新名' } })
    expect(success).toBe(true)
  })

  it('handlePlanChange 在 activePlanId 为空时返回 false', async () => {
    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()
    const activePlanId = ref('')

    const savePlanField = async (changes: Record<string, any>): Promise<boolean> => {
      if (!activePlanId.value) return false
      try {
        await api.updatePlan(activePlanId.value, changes)
        return true
      } catch {
        return false
      }
    }

    const success = await savePlanField({ Info: { Name: '新名' } })
    expect(success).toBe(false)
    expect(mockService.updatePlanApiPlanUpdatePost).not.toHaveBeenCalled()
  })

  it('handleCopyPlan 失败时补偿删除临时计划', async () => {
    // 模拟 plan/index.vue 的 handleCopyPlan 流程
    // 1. getPlans 源计划成功
    // 2. createPlan 新计划成功
    // 3. updatePlan 复制数据失败
    // 4. 补偿调用 deletePlan 清理
    mockService.getPlanApiPlanGetPost.mockResolvedValue({
      code: 200,
      index: [{ uid: 'source-1', type: 'MaaPlanConfig' }],
      data: {
        'source-1': {
          Info: { Name: '源计划', Mode: 'ALL' },
          ALL: { Stage: '1-7' },
        },
      },
    })
    mockService.addPlanApiPlanAddPost.mockResolvedValue({
      code: 200,
      planId: 'temp-new',
    })
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 500,
      message: '复制数据失败',
    })
    mockService.deletePlanApiPlanDeletePost.mockResolvedValue({
      code: 200,
      message: '',
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()
    const planList = ref<{ id: string; name: string; type: string }[]>([])

    let cleanupFailed = false
    let cleanupCalled = false

    // 复刻 handleCopyPlan 的核心逻辑
    let createdPlanId = ''
    try {
      const sourceResponse = await api.getPlans('source-1')
      const sourcePlan = sourceResponse.data['source-1']
      if (!sourcePlan) throw new Error('源计划数据不存在')

      const createResponse = await api.createPlan('MaaPlanConfig')
      const newPlanId = createResponse.planId
      createdPlanId = newPlanId

      const copyData = JSON.parse(JSON.stringify(sourcePlan))
      if (copyData.Info) {
        copyData.Info.Name = '源计划 副本'
      }

      await api.updatePlan(newPlanId, copyData)

      planList.value.push({
        id: newPlanId,
        name: '源计划 副本',
        type: 'MaaPlanConfig',
      })
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`复制计划失败: ${errorMsg}`)
      if (createdPlanId) {
        try {
          await api.deletePlan(createdPlanId)
          cleanupCalled = true
        } catch (cleanupError) {
          cleanupFailed = true
          const cleanupMessage =
            cleanupError instanceof Error ? cleanupError.message : String(cleanupError)
          logger.error(`清理复制失败产生的计划 ${createdPlanId} 失败: ${cleanupMessage}`)
        }
      }
    }

    // 验证：临时计划被补偿删除
    expect(cleanupCalled).toBe(true)
    expect(cleanupFailed).toBe(false)
    expect(planList.value).toHaveLength(0)
    expect(mockService.deletePlanApiPlanDeletePost).toHaveBeenCalledWith({
      planId: 'temp-new',
    })
  })

  it('handleCopyPlan 补偿删除失败时不抛异常且提示用户', async () => {
    mockService.getPlanApiPlanGetPost.mockResolvedValue({
      code: 200,
      index: [{ uid: 'source-1', type: 'MaaPlanConfig' }],
      data: { 'source-1': { Info: { Name: '源', Mode: 'ALL' } } },
    })
    mockService.addPlanApiPlanAddPost.mockResolvedValue({
      code: 200,
      planId: 'temp-new',
    })
    mockService.updatePlanApiPlanUpdatePost.mockResolvedValue({
      code: 500,
      message: '复制失败',
    })
    mockService.deletePlanApiPlanDeletePost.mockResolvedValue({
      code: 500,
      message: '删除也失败',
    })

    const { usePlanApi } = await loadUsePlanApi()
    const api = usePlanApi()

    let cleanupFailed = false
    let createdPlanId = ''

    try {
      const sourceResponse = await api.getPlans('source-1')
      const sourcePlan = sourceResponse.data['source-1']
      const createResponse = await api.createPlan('MaaPlanConfig')
      createdPlanId = createResponse.planId
      await api.updatePlan(createdPlanId, sourcePlan as Record<string, Record<string, any>>)
    } catch {
      if (createdPlanId) {
        try {
          await api.deletePlan(createdPlanId)
        } catch {
          cleanupFailed = true
        }
      }
    }

    expect(cleanupFailed).toBe(true)
  })
})

/**
 * Lane 8：usePlanDataCoordinator 快照与恢复测试。
 *
 * 覆盖：
 * - getConfig 读取指定字段
 * - snapshotTimeConfig 保存时间维度配置
 * - restoreTimeConfig 从快照恢复
 * - updateConfig 修改字段
 * - snapshot 后修改再恢复，值回到原状
 */
describe('Lane 8 usePlanDataCoordinator 快照与恢复', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
    // 预置关卡选项缓存，避免 fromApiData 推断自定义关卡时调用 API
    // 通过 vi.mock 替换 getCachedStageOptions 太复杂，这里直接验证核心方法
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getConfig 返回指定时间维度的字段值', async () => {
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    // 初始化后默认值
    expect(coordinator.getConfig('ALL', 'MedicineNumb')).toBe(0)
    expect(coordinator.getConfig('ALL', 'SeriesNumb')).toBe('0')
    expect(coordinator.getConfig('ALL', 'Stage')).toBe('-')
  })

  it('updateConfig 修改字段后 getConfig 返回新值', async () => {
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    coordinator.updateConfig('Monday', 'MedicineNumb', 5)
    expect(coordinator.getConfig('Monday', 'MedicineNumb')).toBe(5)

    coordinator.updateConfig('Monday', 'Stage', '1-7')
    expect(coordinator.getConfig('Monday', 'Stage')).toBe('1-7')

    coordinator.updateConfig('Monday', 'Stage_1', 'CE-6')
    expect(coordinator.getConfig('Monday', 'Stage_1')).toBe('CE-6')
  })

  it('snapshotTimeConfig 保存当前时间维度配置', async () => {
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    coordinator.updateConfig('Tuesday', 'MedicineNumb', 3)
    coordinator.updateConfig('Tuesday', 'Stage', '1-7')
    coordinator.updateConfig('Tuesday', 'Stage_2', 'CA-5')

    const snapshot = coordinator.snapshotTimeConfig('Tuesday')
    expect(snapshot).not.toBeNull()
    expect(snapshot!.medicineNumb).toBe(3)
    expect(snapshot!.stages.primary).toBe('1-7')
    expect(snapshot!.stages.backup2).toBe('CA-5')
  })

  it('restoreTimeConfig 从快照恢复配置', async () => {
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    // 设置初始值
    coordinator.updateConfig('Wednesday', 'MedicineNumb', 2)
    coordinator.updateConfig('Wednesday', 'Stage', '1-7')
    const snapshot = coordinator.snapshotTimeConfig('Wednesday')

    // 修改值
    coordinator.updateConfig('Wednesday', 'MedicineNumb', 99)
    coordinator.updateConfig('Wednesday', 'Stage', 'CE-6')
    expect(coordinator.getConfig('Wednesday', 'MedicineNumb')).toBe(99)

    // 恢复
    coordinator.restoreTimeConfig('Wednesday', snapshot)
    expect(coordinator.getConfig('Wednesday', 'MedicineNumb')).toBe(2)
    expect(coordinator.getConfig('Wednesday', 'Stage')).toBe('1-7')
  })

  it('snapshot 为 null 时 restoreTimeConfig 不抛异常', async () => {
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    expect(() => coordinator.restoreTimeConfig('Thursday', null)).not.toThrow()
  })

  it('getConfig 对不存在的字段返回 undefined', async () => {
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    expect(coordinator.getConfig('ALL', 'NonExistentField')).toBeUndefined()
  })

  it('snapshotTimeConfig 对未初始化的 timeKey 返回 null', async () => {
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    // 模拟 timeKey 未初始化（正常情况下 initializeTimeConfigs 会初始化所有）
    // 这里通过 delete 模拟
    delete (coordinator.planData.timeConfigs as any).Friday
    const snapshot = coordinator.snapshotTimeConfig('Friday')
    expect(snapshot).toBeNull()
  })

  it('updateConfig + 失败回滚的契约：修改后恢复到旧值', async () => {
    // 模拟 MaaPlanTable.vue 的 updateConfigValue 流程
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    // 设置初始值
    coordinator.updateConfig('Saturday', 'Stage', '1-7')
    const oldValue = coordinator.getConfig('Saturday', 'Stage')
    expect(oldValue).toBe('1-7')

    // 修改本地状态
    coordinator.updateConfig('Saturday', 'Stage', 'CE-6')
    expect(coordinator.getConfig('Saturday', 'Stage')).toBe('CE-6')

    // 模拟 API 失败，回滚
    const apiSuccess = false
    if (!apiSuccess && oldValue !== undefined) {
      coordinator.updateConfig('Saturday', 'Stage', oldValue)
    }

    expect(coordinator.getConfig('Saturday', 'Stage')).toBe('1-7')
  })

  it('toggleStage + snapshot + restore：批量操作回滚契约', async () => {
    // 模拟 MaaPlanTable.vue 的 handleStageToggle 流程。
    // 注意：toggleStage 内部会调用 reassignSlotsBySimpleViewOrder，
    // 该函数只保留在 customStageDefinitions 或 ALL 缓存中已知的关卡。
    // 测试环境未加载 ALL 缓存，因此必须先注册自定义关卡才能验证 toggle 生效。
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    // 先注册一个自定义关卡，使 toggleStage 能识别它
    coordinator.updateCustomStageDefinition(1, 'custom-stage-1')

    // 初始状态：所有槽位为 '-'
    const snapshot = coordinator.snapshotTimeConfig('Sunday')
    expect(snapshot!.stages.primary).toBe('-')

    // 启用自定义关卡
    coordinator.toggleStage('custom-stage-1', 'Sunday', true)
    expect(coordinator.getConfig('Sunday', 'Stage')).toBe('custom-stage-1')

    // 模拟 API 失败，回滚
    const apiSuccess = false
    if (!apiSuccess) {
      coordinator.restoreTimeConfig('Sunday', snapshot)
    }

    expect(coordinator.getConfig('Sunday', 'Stage')).toBe('-')
  })

  it('updateCustomStageDefinition 修改后可通过再次调用回滚到旧值', async () => {
    // 模拟 MaaPlanTable.vue 的 saveCustomStage 失败回滚
    const { usePlanDataCoordinator } = await loadCoordinator()
    const coordinator = usePlanDataCoordinator()

    // 初始定义
    coordinator.updateCustomStageDefinition(1, 'old-stage')
    expect(coordinator.planData.customStageDefinitions.custom_stage_1).toBe('old-stage')

    // 修改为新值
    coordinator.updateCustomStageDefinition(1, 'new-stage')
    expect(coordinator.planData.customStageDefinitions.custom_stage_1).toBe('new-stage')

    // 模拟 saveCustomStage 失败，回滚到旧值
    coordinator.updateCustomStageDefinition(1, 'old-stage')
    expect(coordinator.planData.customStageDefinitions.custom_stage_1).toBe('old-stage')
  })
})
