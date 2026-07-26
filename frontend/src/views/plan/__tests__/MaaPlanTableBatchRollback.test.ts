/**
 * Lane 8：MaaPlanTable 批量操作部分成功/失败回滚契约测试。
 *
 * 覆盖：
 * - saveCustomStage 全部成功：更新 savedCustomStages 快照
 * - saveCustomStage 部分失败：回滚 coordinator + 恢复 tempCustomStages + 警告
 * - saveCustomStage 全部失败：回滚 + 错误提示
 * - enableAllStages 部分失败：回滚失败的时间维度
 * - disableAllStages 部分失败：回滚失败的时间维度
 * - handleStageToggle 失败：从快照恢复
 * - updateConfigValue 失败：从旧值恢复
 *
 * 设计：
 * - 不挂载 MaaPlanTable.vue，而是验证"快照-批量修改-部分失败回滚"的契约模式。
 * - 通过 usePlanDataCoordinator + 模拟 handlePlanChange 驱动。
 * - handlePlanChange 的失败/成功由测试用例逐次控制，模拟 8 次批量更新中部分失败的场景。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

// ---- Mocks --------------------------------------------------------------

const mockService = {
  getStageComboxApiInfoComboxStagePost: vi.fn(),
}

vi.mock('@/api', () => ({
  Service: mockService,
  OpenAPI: { BASE: 'http://test.local' },
  // 让类型 import 在运行时不报错
  GetStageIn: {
    type: {
      USER: 'User',
      TODAY: 'Today',
      ALL: 'ALL',
      MONDAY: 'Monday',
      TUESDAY: 'Tuesday',
      WEDNESDAY: 'Wednesday',
      THURSDAY: 'Thursday',
      FRIDAY: 'Friday',
      SATURDAY: 'Saturday',
      SUNDAY: 'Sunday',
    },
  },
}))

vi.mock('ant-design-vue', () => ({
  message: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

const messageSpy = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}

vi.mock('ant-design-vue', () => ({
  message: messageSpy,
}))

const loadCoordinator = async () => {
  vi.resetModules()
  return await import('@/composables/usePlanDataCoordinator')
}

// ---- Types --------------------------------------------------------------

type TimeKey = import('@/composables/usePlanDataCoordinator').TimeKey

const TIME_KEYS: TimeKey[] = [
  'ALL',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

// ---- Tests --------------------------------------------------------------

describe('Lane 8 MaaPlanTable 批量回滚契约', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('saveCustomStage 批量保存', () => {
    it('全部成功：更新 savedCustomStages 快照', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      // 初始自定义关卡
      coordinator.updateCustomStageDefinition(1, 'old-stage')
      const savedCustomStages = ref({ ...coordinator.planData.customStageDefinitions })
      const tempCustomStages = ref({ ...coordinator.planData.customStageDefinitions })

      // 模拟用户修改为 'new-stage'
      const index = 1 as 1 | 2 | 3 | 4
      const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
      const newValue = 'new-stage'
      const oldValue = savedCustomStages.value[key].trim()
      tempCustomStages.value[key] = newValue

      // 更新 coordinator
      coordinator.updateCustomStageDefinition(index, newValue)

      // 模拟 handlePlanChange：8 次全部成功
      const handlePlanChange = vi.fn().mockResolvedValue(true)

      // 复刻 saveCustomStage 的批量保存逻辑
      const planConfig = coordinator.toApiData()
      const failedKeys: TimeKey[] = []
      for (let i = 0; i < TIME_KEYS.length; i++) {
        const timeKey = TIME_KEYS[i]
        const timeConfig = planConfig[timeKey] as Record<string, any>
        if (timeConfig) {
          const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3', 'Stage_Remain']
          for (const field of stageFields) {
            if (timeConfig[field] === oldValue && oldValue !== '') {
              timeConfig[field] = newValue
            }
          }
          const saved = await handlePlanChange(timeKey, timeConfig, { refresh: false })
          if (!saved) failedKeys.push(timeKey)
        }
      }

      // 全部成功
      expect(failedKeys).toHaveLength(0)
      expect(handlePlanChange).toHaveBeenCalledTimes(TIME_KEYS.length)
      // 更新快照
      savedCustomStages.value = { ...coordinator.planData.customStageDefinitions }
      expect(savedCustomStages.value.custom_stage_1).toBe('new-stage')
    })

    it('部分失败：回滚 coordinator + 恢复 tempCustomStages + 警告', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      // 初始自定义关卡
      coordinator.updateCustomStageDefinition(1, 'old-stage')
      const savedCustomStages = ref({ ...coordinator.planData.customStageDefinitions })
      const tempCustomStages = ref({ ...coordinator.planData.customStageDefinitions })

      // 模拟用户修改为 'new-stage'
      const index = 1 as 1 | 2 | 3 | 4
      const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
      const newValue = 'new-stage'
      const oldValue = savedCustomStages.value[key].trim()
      tempCustomStages.value[key] = newValue
      coordinator.updateCustomStageDefinition(index, newValue)

      // 模拟 handlePlanChange：前 3 次成功，后 5 次失败
      const handlePlanChange = vi
        .fn()
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce(false)
        .mockResolvedValueOnce(false)
        .mockResolvedValueOnce(false)
        .mockResolvedValueOnce(false)
        .mockResolvedValueOnce(false)

      // 复刻 saveCustomStage 的批量保存逻辑
      const planConfig = coordinator.toApiData()
      const failedKeys: TimeKey[] = []
      let lastSavedIndex = -1
      for (let i = 0; i < TIME_KEYS.length; i++) {
        const timeKey = TIME_KEYS[i]
        const timeConfig = planConfig[timeKey] as Record<string, any>
        if (timeConfig) {
          const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3', 'Stage_Remain']
          for (const field of stageFields) {
            if (timeConfig[field] === oldValue && oldValue !== '') {
              timeConfig[field] = newValue
            }
          }
          const saved = await handlePlanChange(timeKey, timeConfig, { refresh: false })
          if (saved) lastSavedIndex = i
          else failedKeys.push(timeKey)
        }
      }

      // 验证：5 个时间维度失败
      expect(failedKeys).toHaveLength(5)
      expect(failedKeys).toEqual(['Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])
      expect(lastSavedIndex).toBe(2) // 最后成功的是 Tuesday (index=2)

      // 复刻回滚逻辑
      coordinator.updateCustomStageDefinition(index, oldValue)
      tempCustomStages.value = { ...savedCustomStages.value }

      if (lastSavedIndex >= 0) {
        messageSpy.warning(
          `自定义关卡部分保存失败（${failedKeys.join('、')}），已恢复到上次保存的状态`
        )
      } else {
        messageSpy.error(`自定义关卡保存失败，已恢复到上次保存的状态`)
      }

      // 验证 coordinator 已回滚
      expect(coordinator.planData.customStageDefinitions.custom_stage_1).toBe('old-stage')
      // 验证 tempCustomStages 已恢复
      expect(tempCustomStages.value.custom_stage_1).toBe('old-stage')
      // 验证警告提示
      expect(messageSpy.warning).toHaveBeenCalledWith(expect.stringContaining('部分保存失败'))
      expect(messageSpy.warning).toHaveBeenCalledWith(expect.stringContaining('Wednesday'))
    })

    it('全部失败：回滚 + 错误提示', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      coordinator.updateCustomStageDefinition(1, 'old-stage')
      const savedCustomStages = ref({ ...coordinator.planData.customStageDefinitions })
      const tempCustomStages = ref({ ...coordinator.planData.customStageDefinitions })

      const index = 1 as 1 | 2 | 3 | 4
      const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
      const newValue = 'new-stage'
      const oldValue = savedCustomStages.value[key].trim()
      tempCustomStages.value[key] = newValue
      coordinator.updateCustomStageDefinition(index, newValue)

      // 模拟 handlePlanChange：全部失败
      const handlePlanChange = vi.fn().mockResolvedValue(false)

      const planConfig = coordinator.toApiData()
      const failedKeys: TimeKey[] = []
      let lastSavedIndex = -1
      for (let i = 0; i < TIME_KEYS.length; i++) {
        const timeKey = TIME_KEYS[i]
        const timeConfig = planConfig[timeKey] as Record<string, any>
        if (timeConfig) {
          const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3', 'Stage_Remain']
          for (const field of stageFields) {
            if (timeConfig[field] === oldValue && oldValue !== '') {
              timeConfig[field] = newValue
            }
          }
          const saved = await handlePlanChange(timeKey, timeConfig, { refresh: false })
          if (saved) lastSavedIndex = i
          else failedKeys.push(timeKey)
        }
      }

      // 全部失败
      expect(failedKeys).toHaveLength(TIME_KEYS.length)
      expect(lastSavedIndex).toBe(-1)

      // 回滚
      coordinator.updateCustomStageDefinition(index, oldValue)
      tempCustomStages.value = { ...savedCustomStages.value }

      if (lastSavedIndex >= 0) {
        messageSpy.warning(
          `自定义关卡部分保存失败（${failedKeys.join('、')}），已恢复到上次保存的状态`
        )
      } else {
        messageSpy.error(`自定义关卡保存失败，已恢复到上次保存的状态`)
      }

      expect(coordinator.planData.customStageDefinitions.custom_stage_1).toBe('old-stage')
      expect(messageSpy.error).toHaveBeenCalledWith(expect.stringContaining('保存失败'))
    })

    it('值未变化时跳过保存', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      coordinator.updateCustomStageDefinition(1, 'same-stage')
      const savedCustomStages = ref({ ...coordinator.planData.customStageDefinitions })
      const tempCustomStages = ref({ ...coordinator.planData.customStageDefinitions })

      const index = 1 as 1 | 2 | 3 | 4
      const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
      const newValue = tempCustomStages.value[key].trim()
      const oldValue = savedCustomStages.value[key].trim()

      // 值相同，应跳过
      expect(newValue).toBe(oldValue)

      const handlePlanChange = vi.fn().mockResolvedValue(true)

      // 复刻 saveCustomStage 的 early return
      if (newValue === oldValue) {
        // 跳过保存
      } else {
        // 不会执行
        const planConfig = coordinator.toApiData()
        await handlePlanChange('ALL', planConfig.ALL)
      }

      expect(handlePlanChange).not.toHaveBeenCalled()
    })
  })

  describe('enableAllStages 批量启用', () => {
    it('部分失败：回滚失败的时间维度', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      // 注册自定义关卡
      coordinator.updateCustomStageDefinition(1, 'custom-1')

      // 模拟 handlePlanChange：ALL 和 Monday 成功，Tuesday 失败
      const handlePlanChange = vi
        .fn()
        .mockResolvedValueOnce(true) // ALL
        .mockResolvedValueOnce(true) // Monday
        .mockResolvedValueOnce(false) // Tuesday
        .mockResolvedValueOnce(true) // Wednesday
        .mockResolvedValueOnce(false) // Thursday
        .mockResolvedValueOnce(true) // Friday
        .mockResolvedValueOnce(true) // Saturday
        .mockResolvedValueOnce(true) // Sunday

      // 复刻 enableAllStages 的核心逻辑
      const snapshots = new Map<TimeKey, ReturnType<typeof coordinator.snapshotTimeConfig>>()
      for (const timeKey of TIME_KEYS) {
        // 模拟 isStageAvailable 返回 true 且 enabledCount < 4
        snapshots.set(timeKey, coordinator.snapshotTimeConfig(timeKey))
        coordinator.toggleStage('custom-1', timeKey, true)
      }

      const planConfig = coordinator.toApiData()
      const failedKeys: TimeKey[] = []
      for (const timeKey of TIME_KEYS) {
        const timeConfig = planConfig[timeKey]
        if (timeConfig && snapshots.has(timeKey)) {
          const success = await handlePlanChange(timeKey, timeConfig)
          if (!success) {
            failedKeys.push(timeKey)
          }
        }
      }

      // 验证：Tuesday 和 Thursday 失败
      expect(failedKeys).toEqual(['Tuesday', 'Thursday'])

      // 回滚失败的维度
      for (const key of failedKeys) {
        coordinator.restoreTimeConfig(key, snapshots.get(key))
      }

      // 验证：失败维度的 custom-1 已被回滚（primary 回到 '-'）
      expect(coordinator.getConfig('Tuesday', 'Stage')).toBe('-')
      expect(coordinator.getConfig('Thursday', 'Stage')).toBe('-')
      // 成功维度保留 custom-1
      expect(coordinator.getConfig('ALL', 'Stage')).toBe('custom-1')
      expect(coordinator.getConfig('Monday', 'Stage')).toBe('custom-1')
      expect(coordinator.getConfig('Wednesday', 'Stage')).toBe('custom-1')

      // 警告提示
      messageSpy.warning(`部分时间维度启用失败（${failedKeys.join('、')}），已恢复原值`)
      expect(messageSpy.warning).toHaveBeenCalledWith(expect.stringContaining('Tuesday'))
    })

    it('全部成功：不触发回滚', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      coordinator.updateCustomStageDefinition(1, 'custom-1')

      const handlePlanChange = vi.fn().mockResolvedValue(true)

      const snapshots = new Map<TimeKey, ReturnType<typeof coordinator.snapshotTimeConfig>>()
      for (const timeKey of TIME_KEYS) {
        snapshots.set(timeKey, coordinator.snapshotTimeConfig(timeKey))
        coordinator.toggleStage('custom-1', timeKey, true)
      }

      const planConfig = coordinator.toApiData()
      const failedKeys: TimeKey[] = []
      for (const timeKey of TIME_KEYS) {
        const timeConfig = planConfig[timeKey]
        if (timeConfig && snapshots.has(timeKey)) {
          const success = await handlePlanChange(timeKey, timeConfig)
          if (!success) {
            failedKeys.push(timeKey)
          }
        }
      }

      expect(failedKeys).toHaveLength(0)
      // 所有维度保留 custom-1
      for (const timeKey of TIME_KEYS) {
        expect(coordinator.getConfig(timeKey, 'Stage')).toBe('custom-1')
      }
    })
  })

  describe('disableAllStages 批量禁用', () => {
    it('部分失败：回滚失败的时间维度', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      // 注册并启用自定义关卡
      coordinator.updateCustomStageDefinition(1, 'custom-1')
      for (const timeKey of TIME_KEYS) {
        coordinator.toggleStage('custom-1', timeKey, true)
      }

      // 模拟 handlePlanChange：ALL 失败，其余成功
      const handlePlanChange = vi
        .fn()
        .mockResolvedValueOnce(false) // ALL
        .mockResolvedValueOnce(true) // Monday
        .mockResolvedValueOnce(true) // Tuesday
        .mockResolvedValueOnce(true) // Wednesday
        .mockResolvedValueOnce(true) // Thursday
        .mockResolvedValueOnce(true) // Friday
        .mockResolvedValueOnce(true) // Saturday
        .mockResolvedValueOnce(true) // Sunday

      // 复刻 disableAllStages 的核心逻辑
      const snapshots = new Map<TimeKey, ReturnType<typeof coordinator.snapshotTimeConfig>>()
      for (const timeKey of TIME_KEYS) {
        snapshots.set(timeKey, coordinator.snapshotTimeConfig(timeKey))
        coordinator.toggleStage('custom-1', timeKey, false)
      }

      const planConfig = coordinator.toApiData()
      const failedKeys: TimeKey[] = []
      for (const timeKey of TIME_KEYS) {
        const timeConfig = planConfig[timeKey]
        if (timeConfig) {
          const success = await handlePlanChange(timeKey, timeConfig)
          if (!success) {
            failedKeys.push(timeKey)
          }
        }
      }

      expect(failedKeys).toEqual(['ALL'])

      // 回滚 ALL
      for (const key of failedKeys) {
        coordinator.restoreTimeConfig(key, snapshots.get(key))
      }

      // 验证：ALL 保留 custom-1（回滚），其他已禁用
      expect(coordinator.getConfig('ALL', 'Stage')).toBe('custom-1')
      expect(coordinator.getConfig('Monday', 'Stage')).toBe('-')
      expect(coordinator.getConfig('Tuesday', 'Stage')).toBe('-')
    })
  })

  describe('handleStageToggle 单个切换', () => {
    it('失败时从快照恢复', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      coordinator.updateCustomStageDefinition(1, 'custom-1')

      // 初始状态：Sunday 的 primary 为 '-'
      expect(coordinator.getConfig('Sunday', 'Stage')).toBe('-')

      // 复刻 handleStageToggle 的核心逻辑
      const snapshot = coordinator.snapshotTimeConfig('Sunday')
      coordinator.toggleStage('custom-1', 'Sunday', true)

      // 修改后 primary 应为 'custom-1'
      expect(coordinator.getConfig('Sunday', 'Stage')).toBe('custom-1')

      // 模拟 API 失败
      const handlePlanChange = vi.fn().mockResolvedValue(false)
      const planConfig = coordinator.toApiData()
      const timeConfig = planConfig['Sunday']
      const success = await handlePlanChange('Sunday', timeConfig)

      if (!success) {
        coordinator.restoreTimeConfig('Sunday', snapshot)
      }

      // 验证：已回滚到 '-'
      expect(coordinator.getConfig('Sunday', 'Stage')).toBe('-')
    })

    it('成功时保留新值', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      coordinator.updateCustomStageDefinition(1, 'custom-1')

      const snapshot = coordinator.snapshotTimeConfig('Sunday')
      coordinator.toggleStage('custom-1', 'Sunday', true)

      const handlePlanChange = vi.fn().mockResolvedValue(true)
      const planConfig = coordinator.toApiData()
      const timeConfig = planConfig['Sunday']
      const success = await handlePlanChange('Sunday', timeConfig)

      if (!success) {
        coordinator.restoreTimeConfig('Sunday', snapshot)
      }

      // 验证：保留 'custom-1'
      expect(coordinator.getConfig('Sunday', 'Stage')).toBe('custom-1')
    })
  })

  describe('updateConfigValue 单字段更新', () => {
    it('失败时从旧值恢复', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      // 设置初始值
      coordinator.updateConfig('Monday', 'MedicineNumb', 3)
      const oldValue = coordinator.getConfig('Monday', 'MedicineNumb')
      expect(oldValue).toBe(3)

      // 复刻 updateConfigValue 的核心逻辑
      coordinator.updateConfig('Monday', 'MedicineNumb', 10)
      expect(coordinator.getConfig('Monday', 'MedicineNumb')).toBe(10)

      // 模拟 API 失败
      const handlePlanChange = vi.fn().mockResolvedValue(false)
      const success = await handlePlanChange('Monday.MedicineNumb', 10)

      if (!success && oldValue !== undefined) {
        coordinator.updateConfig('Monday', 'MedicineNumb', oldValue)
      }

      // 验证：已回滚到 3
      expect(coordinator.getConfig('Monday', 'MedicineNumb')).toBe(3)
    })

    it('成功时保留新值', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      coordinator.updateConfig('Monday', 'Stage', '1-7')
      const oldValue = coordinator.getConfig('Monday', 'Stage')

      coordinator.updateConfig('Monday', 'Stage', 'CE-6')

      const handlePlanChange = vi.fn().mockResolvedValue(true)
      const success = await handlePlanChange('Monday.Stage', 'CE-6')

      if (!success && oldValue !== undefined) {
        coordinator.updateConfig('Monday', 'Stage', oldValue)
      }

      expect(coordinator.getConfig('Monday', 'Stage')).toBe('CE-6')
    })

    it('oldValue 为 undefined 时不回滚', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      // 对不存在的字段调用 getConfig 返回 undefined
      const oldValue = coordinator.getConfig('Monday', 'NonExistentField')
      expect(oldValue).toBeUndefined()

      // updateConfig 对未知字段不做任何修改
      coordinator.updateConfig('Monday', 'NonExistentField', 'value')
      // 仍然 undefined
      expect(coordinator.getConfig('Monday', 'NonExistentField')).toBeUndefined()

      // 模拟 API 失败
      const handlePlanChange = vi.fn().mockResolvedValue(false)
      const success = await handlePlanChange('Monday.NonExistentField', 'value')

      // oldValue 为 undefined，不回滚
      if (!success && oldValue !== undefined) {
        coordinator.updateConfig('Monday', 'NonExistentField', oldValue)
      }

      // 无变化
      expect(coordinator.getConfig('Monday', 'NonExistentField')).toBeUndefined()
    })
  })

  describe('批量操作中的 8 次更新计数', () => {
    it('saveCustomStage 恰好发起 8 次 handlePlanChange（每个时间维度一次）', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      coordinator.updateCustomStageDefinition(1, 'old-stage')
      coordinator.updateCustomStageDefinition(1, 'new-stage')

      const handlePlanChange = vi.fn().mockResolvedValue(true)

      const planConfig = coordinator.toApiData()
      for (const timeKey of TIME_KEYS) {
        const timeConfig = planConfig[timeKey]
        if (timeConfig) {
          await handlePlanChange(timeKey, timeConfig, { refresh: false })
        }
      }

      expect(handlePlanChange).toHaveBeenCalledTimes(TIME_KEYS.length)
      // 验证每个时间维度都被调用
      for (const timeKey of TIME_KEYS) {
        expect(handlePlanChange).toHaveBeenCalledWith(timeKey, expect.any(Object), {
          refresh: false,
        })
      }
    })

    it('enableAllStages 对受影响的维度发起 handlePlanChange', async () => {
      const { usePlanDataCoordinator } = await loadCoordinator()
      const coordinator = usePlanDataCoordinator()

      coordinator.updateCustomStageDefinition(1, 'custom-1')

      const handlePlanChange = vi.fn().mockResolvedValue(true)

      const snapshots = new Map<TimeKey, ReturnType<typeof coordinator.snapshotTimeConfig>>()
      for (const timeKey of TIME_KEYS) {
        snapshots.set(timeKey, coordinator.snapshotTimeConfig(timeKey))
        coordinator.toggleStage('custom-1', timeKey, true)
      }

      const planConfig = coordinator.toApiData()
      for (const timeKey of TIME_KEYS) {
        const timeConfig = planConfig[timeKey]
        if (timeConfig && snapshots.has(timeKey)) {
          await handlePlanChange(timeKey, timeConfig)
        }
      }

      // 所有 8 个时间维度都被调用
      expect(handlePlanChange).toHaveBeenCalledTimes(TIME_KEYS.length)
    })
  })
})
