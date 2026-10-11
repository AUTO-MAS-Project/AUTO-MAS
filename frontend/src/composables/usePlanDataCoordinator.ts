/**
 * 计划表数据协调层
 *
 * 作为前端架构中的"交通指挥中心"，负责：
 * 1. 统一管理数据流
 * 2. 协调视图间的同步
 * 3. 处理与后端的通信
 * 4. 提供统一的数据访问接口
 */

import { ref, computed } from 'vue'
import type { MaaPlanConfig_Item, ComboBoxItem } from '@/api'
import { Service } from '@/api'
import { GetStageIn } from '@/api'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
import { planColumnKeys, readPlanColumn, type PlanMode } from '@/utils/planDays'
const logger = window.electronAPI.getLogger('计划数据协调器')

// 时间维度常量。这里只列一周七天：多天轮换的天键是 "1"~"N"，由计划表数据决定，不在常量里。
export const TIME_KEYS = [
  'ALL',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const
export type TimeKey = (typeof TIME_KEYS)[number]

/**
 * 天键 → 关卡池键。
 *
 * 关卡池接口仍按 ALL + 星期名给池子（后端没改）：周计划的天本身就是星期名，直接用自己的池；
 * 多天轮换的第 i 天与真实星期没有对应关系，拿不到属于它的池，所以所有轮换天都读 ALL 池。
 */
const stagePoolKeyOf = (dayKey: string): TimeKey =>
  (TIME_KEYS as readonly string[]).includes(dayKey) ? (dayKey as TimeKey) : 'ALL'

// 一天的配置
interface PlanDayConfig {
  medicineNumb: number
  seriesNumb: string
  stages: {
    primary: string // Stage
    backup1: string // Stage_1
    backup2: string // Stage_2
    backup3: string // Stage_3
  }
}

// 统一的数据结构
interface PlanDataState {
  // 基础信息
  info: {
    name: string
    mode: PlanMode
    type: string
  }

  // 按天的配置数据。天键由计划表自己的模式与轮换天数决定：
  // 周计划是 Monday~Sunday，多天轮换是 "1"~"N"，ALL 一直在。
  timeConfigs: Record<string, PlanDayConfig>

  // 自定义关卡定义
  customStageDefinitions: {
    custom_stage_1: string
    custom_stage_2: string
    custom_stage_3: string
    custom_stage_4: string
  }
}

// 标准关卡选项缓存（按关卡池键：ALL 或星期名）
const stageOptionsCache = ref<Record<string, ComboBoxItem[]>>({})
let stageOptionsPreloadPromise: Promise<void> | null = null
// 缓存代次：clearStageOptionsCache 自增，清缓存前发出的请求完成后不得写入新缓存
let stageOptionsGeneration = 0

// 加载标准关卡选项，参数是关卡池键（ALL 或星期名）
async function loadStageOptions(poolKey: TimeKey): Promise<ComboBoxItem[]> {
  // 如果已缓存，直接返回
  if (stageOptionsCache.value[poolKey]) {
    return stageOptionsCache.value[poolKey]
  }

  const generation = stageOptionsGeneration

  try {
    // 映射时间维度到 API 参数
    const typeMap: Record<TimeKey, GetStageIn.type> = {
      ALL: GetStageIn.type.ALL,
      Monday: GetStageIn.type.MONDAY,
      Tuesday: GetStageIn.type.TUESDAY,
      Wednesday: GetStageIn.type.WEDNESDAY,
      Thursday: GetStageIn.type.THURSDAY,
      Friday: GetStageIn.type.FRIDAY,
      Saturday: GetStageIn.type.SATURDAY,
      Sunday: GetStageIn.type.SUNDAY,
    }

    const response = await Service.getStageComboxApiInfoComboxStagePost({
      type: typeMap[poolKey],
    })

    if (response.code === 200 || response.code === undefined) {
      // 缓存已被清除：丢弃过期响应，避免旧数据覆盖刷新后的新缓存
      if (generation !== stageOptionsGeneration) {
        return []
      }
      // 缓存结果
      stageOptionsCache.value[poolKey] = response.data
      return response.data
    } else {
      logger.error(`加载失败 (${poolKey}): ${response.message}`)
      return []
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载异常 (${poolKey}): ${errorMsg}`)
    return []
  }
}

// 预加载关卡选项。传入当前的天键集合时只拉这些天真正会读的池，缺省拉全部池。
export async function preloadAllStageOptions(dayKeys?: readonly string[]): Promise<void> {
  const poolKeys = [...new Set((dayKeys ?? TIME_KEYS).map(stagePoolKeyOf))]
  const hasCompleteCache = poolKeys.every(poolKey =>
    Array.isArray(stageOptionsCache.value[poolKey])
  )
  if (hasCompleteCache) {
    return
  }

  if (!stageOptionsPreloadPromise) {
    const generation = stageOptionsGeneration
    const preloadPromise: Promise<void> = Promise.all(
      poolKeys.map(poolKey => loadStageOptions(poolKey))
    )
      .then(() => {
        if (generation === stageOptionsGeneration) {
          logger.info('关卡选项预加载完成')
        }
      })
      .finally(() => {
        // 仅清理自己持有的 promise：refresh 后启动的新 preload 不应被过期轮次清掉
        if (stageOptionsPreloadPromise === preloadPromise) {
          stageOptionsPreloadPromise = null
        }
      })
    stageOptionsPreloadPromise = preloadPromise
  }

  await stageOptionsPreloadPromise
}

// 清除缓存（用于刷新数据）
export function clearStageOptionsCache(): void {
  // 自增代次，使清缓存前发出的在途请求全部失效
  stageOptionsGeneration += 1
  stageOptionsCache.value = {}
  stageOptionsPreloadPromise = null
  logger.info('关卡选项缓存已清除')
}

// 获取缓存的关卡选项。参数可以是任意天键：轮换天没有自己的池，会落到 ALL 池。
export function getCachedStageOptions(dayKey: string): ComboBoxItem[] {
  return stageOptionsCache.value[stagePoolKeyOf(dayKey)] || []
}

/**
 * 计划表数据协调器
 */
export function usePlanDataCoordinator() {
  // 当前计划表ID
  const currentPlanId = ref<string>('default')

  // 当前计划表的天键（含 ALL）：由接口数据的 Info.Mode 与 Info.RotateDays 决定，
  // 周计划是星期名，多天轮换是 "1"~"N"。本地结构、视图数据都按它来。
  const dayKeys = ref<string[]>([...TIME_KEYS])

  const getDefaultCustomStageDefinitions = () => ({
    custom_stage_1: '',
    custom_stage_2: '',
    custom_stage_3: '',
    custom_stage_4: '',
  })

  /** 空的一天 */
  const createEmptyDayConfig = (): PlanDayConfig => ({
    medicineNumb: 0,
    seriesNumb: '0',
    stages: {
      primary: '-',
      backup1: '-',
      backup2: '-',
      backup3: '-',
    },
  })

  /** 接口里的一天 → 本地结构；该天还没有数据时给一份空的（天键刚换、后端尚未落盘时会遇到） */
  const toDayConfig = (timeData: MaaPlanConfig_Item | null | undefined): PlanDayConfig => ({
    medicineNumb: timeData?.MedicineNumb || 0,
    seriesNumb: timeData?.SeriesNumb || '0',
    stages: {
      primary: timeData?.Stage || '-',
      backup1: timeData?.Stage_1 || '-',
      backup2: timeData?.Stage_2 || '-',
      backup3: timeData?.Stage_3 || '-',
    },
  })

  // 单一数据源
  const planData = ref<PlanDataState>({
    info: {
      name: '',
      mode: 'ALL',
      type: PLAN_CONFIG_TYPES.MAA,
    },
    timeConfigs: {},
    customStageDefinitions: getDefaultCustomStageDefinitions(),
  })

  // 按当前天键重建时间配置
  const initializeTimeConfigs = () => {
    planData.value.timeConfigs = Object.fromEntries(
      dayKeys.value.map(dayKey => [dayKey, createEmptyDayConfig()])
    )
  }

  // 初始化数据
  initializeTimeConfigs()

  // 从API数据转换为内部数据结构
  const fromApiData = (
    apiData: Record<string, any>,
    forceUpdateCustomStages = false,
    inferCustomStages = true
  ) => {
    // 更新基础信息
    if (apiData.Info) {
      planData.value.info.name = apiData.Info.Name || ''
      planData.value.info.mode = (apiData.Info.Mode || 'ALL') as PlanMode

      // 如果API数据中包含计划表ID信息，更新当前planId
      // 注意：这里假设planId通过其他方式传入，API数据本身可能不包含ID
    }

    // 天键跟着计划表的模式与轮换天数走：切换模式或改天数会整套换键（星期名 ↔ "1"~"N"），
    // 所以这里连本地结构一起重建。旧模式的天不能留着，否则 toApiData 会把它们当成当前的天写回接口。
    dayKeys.value = planColumnKeys(planData.value.info.mode, apiData.Info?.RotateDays)
    planData.value.timeConfigs = Object.fromEntries(
      dayKeys.value.map(dayKey => [
        dayKey,
        toDayConfig(readPlanColumn(apiData, dayKey) as MaaPlanConfig_Item | null),
      ])
    )

    if (!inferCustomStages) {
      return
    }

    // 从所有时间配置中推断自定义关卡定义
    const inferredStages = new Set<string>()

    dayKeys.value.forEach(timeKey => {
      const timeData = readPlanColumn(apiData, timeKey) as MaaPlanConfig_Item | null
      if (timeData) {
        // 检查所有关卡字段
        const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3']
        stageFields.forEach(field => {
          const stageValue = timeData[field as keyof MaaPlanConfig_Item] as string
          if (stageValue && stageValue !== '-') {
            // 如果不是标准关卡，则认为是自定义关卡
            const cachedOptions = getCachedStageOptions(timeKey)
            const isStandardStage = cachedOptions.some(option => option.value === stageValue)
            if (!isStandardStage) {
              inferredStages.add(stageValue)
            }
          }
        })
      }
    })

    // 根据参数决定是否更新自定义关卡定义
    if (forceUpdateCustomStages) {
      // 强制更新：完全从配置推断（用于初始加载或切换计划）
      const inferredArray = Array.from(inferredStages).sort()
      planData.value.customStageDefinitions = {
        custom_stage_1: inferredArray[0] || '',
        custom_stage_2: inferredArray[1] || '',
        custom_stage_3: inferredArray[2] || '',
        custom_stage_4: inferredArray[3] || '',
      }

      if (inferredStages.size > 0) {
        logger.info(
          `从配置数据推断出 ${inferredStages.size} 个自定义关卡: ${Array.from(inferredStages).join(', ')}`
        )
      }
    } else {
      // 智能合并：保留现有定义，只添加新发现的关卡
      const currentCustomStages = new Set<string>()
      Object.values(planData.value.customStageDefinitions).forEach(stage => {
        if (stage && stage.trim()) {
          currentCustomStages.add(stage)
        }
      })

      // 找出新发现的关卡（在推断中但不在当前定义中）
      const newStages = Array.from(inferredStages).filter(stage => !currentCustomStages.has(stage))

      if (newStages.length > 0) {
        // 将新关卡添加到空的槽位中
        const currentDefinitions = { ...planData.value.customStageDefinitions }
        const emptySlots = Object.keys(currentDefinitions).filter(
          key => !currentDefinitions[key as keyof typeof currentDefinitions]
        )

        newStages.forEach((stage, index) => {
          if (index < emptySlots.length) {
            currentDefinitions[emptySlots[index] as keyof typeof currentDefinitions] = stage
          }
        })

        planData.value.customStageDefinitions = currentDefinitions
        logger.info(`添加新发现的自定义关卡: ${newStages.join(', ')}`)
      }
    }
  }

  // 转换为API数据格式。形态与后端 PlanDaysConfig 一致：ALL 仍在顶层，其余天收进 Days，
  // 调用方用 readPlanColumn 取具体某一天（生成的 API 模型还没跟上，这里先按结构拼）。
  const toApiData = (): Record<string, any> => {
    const result: Record<string, any> = {
      Info: {
        Name: planData.value.info.name,
        Mode: planData.value.info.mode,
      },
    }

    dayKeys.value.forEach(timeKey => {
      const config = planData.value.timeConfigs[timeKey]
      if (!config) {
        return
      }

      const day = {
        MedicineNumb: config.medicineNumb,
        SeriesNumb: config.seriesNumb as any,
        Stage: config.stages.primary,
        Stage_1: config.stages.backup1,
        Stage_2: config.stages.backup2,
        Stage_3: config.stages.backup3,
      }

      if (timeKey === 'ALL') {
        result.ALL = day
      } else {
        result.Days = result.Days ?? {}
        result.Days[timeKey] = day
      }
    })

    // 不保存自定义关卡定义到后端，它们会在加载时重新推断

    return result
  }

  // 配置视图数据适配器
  const configViewData = computed(() => {
    return [
      {
        key: 'MedicineNumb',
        taskName: '吃理智药',
        ...Object.fromEntries(
          dayKeys.value.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.medicineNumb || 0,
          ])
        ),
      },
      {
        key: 'SeriesNumb',
        taskName: '连战次数',
        ...Object.fromEntries(
          dayKeys.value.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.seriesNumb || '0',
          ])
        ),
      },
      {
        key: 'Stage',
        taskName: '关卡选择',
        ...Object.fromEntries(
          dayKeys.value.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.primary || '-',
          ])
        ),
      },
      {
        key: 'Stage_1',
        taskName: '备选关卡-1',
        ...Object.fromEntries(
          dayKeys.value.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup1 || '-',
          ])
        ),
      },
      {
        key: 'Stage_2',
        taskName: '备选关卡-2',
        ...Object.fromEntries(
          dayKeys.value.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup2 || '-',
          ])
        ),
      },
      {
        key: 'Stage_3',
        taskName: '备选关卡-3',
        ...Object.fromEntries(
          dayKeys.value.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup3 || '-',
          ])
        ),
      },
    ]
  })

  // 简化视图数据适配器
  const simpleViewData = computed(() => {
    const result: any[] = []

    // 添加自定义关卡
    Object.entries(planData.value.customStageDefinitions).forEach(([, stageName]) => {
      if (stageName && stageName.trim()) {
        const stageStates: Record<string, boolean> = {}
        dayKeys.value.forEach(timeKey => {
          const config = planData.value.timeConfigs[timeKey]
          stageStates[timeKey] = Object.values(config.stages).includes(stageName)
        })

        result.push({
          key: stageName,
          taskName: stageName,
          isCustom: true,
          stageName: stageName,
          ...stageStates,
        })
      }
    })

    // 添加标准关卡（从 ALL 的缓存中获取所有标准关卡）
    const allStageOptions = getCachedStageOptions('ALL')
    allStageOptions
      .filter(option => option.value && option.value !== '-')
      .forEach(option => {
        const stageStates: Record<string, boolean> = {}
        dayKeys.value.forEach(timeKey => {
          const config = planData.value.timeConfigs[timeKey]
          stageStates[timeKey] = Object.values(config.stages).includes(option.value!)
        })

        result.push({
          key: option.value!,
          taskName: option.label,
          isCustom: false,
          stageName: option.value!,
          ...stageStates,
        })
      })

    return result
  })

  // 更新配置数据
  const updateConfig = (timeKey: string, field: string, value: any) => {
    // 天键跟着模式与轮换天数变，重建的间隙里取不到这一天就什么也不做
    const config = planData.value.timeConfigs[timeKey]
    if (!config) {
      return
    }

    if (field === 'MedicineNumb') {
      config.medicineNumb = value
    } else if (field === 'SeriesNumb') {
      config.seriesNumb = value
    } else if (field === 'Stage') {
      config.stages.primary = value
    } else if (field === 'Stage_1') {
      config.stages.backup1 = value
    } else if (field === 'Stage_2') {
      config.stages.backup2 = value
    } else if (field === 'Stage_3') {
      config.stages.backup3 = value
    }
  }

  // 切换关卡状态（简化视图用）
  const toggleStage = (stageName: string, timeKey: string, enabled: boolean) => {
    const config = planData.value.timeConfigs[timeKey]
    const stageSlots = ['primary', 'backup1', 'backup2', 'backup3'] as const

    if (enabled) {
      // 找到第一个空槽位
      const emptySlot = stageSlots.find(slot => !config.stages[slot] || config.stages[slot] === '-')
      if (emptySlot) {
        config.stages[emptySlot] = stageName
      }
      // 启用后重新按简化视图顺序排列
      reassignSlotsBySimpleViewOrder(timeKey)
    } else {
      // 从所有槽位中移除
      stageSlots.forEach(slot => {
        if (config.stages[slot] === stageName) {
          config.stages[slot] = '-'
        }
      })
      // 移除后重新按简化视图顺序排列
      reassignSlotsBySimpleViewOrder(timeKey)
    }
  }

  // 按简化视图顺序重新分配槽位
  const reassignSlotsBySimpleViewOrder = (timeKey: string) => {
    const config = planData.value.timeConfigs[timeKey]
    const stageSlots = ['primary', 'backup1', 'backup2', 'backup3'] as const

    // 收集当前已启用的关卡
    const enabledStages = Object.values(config.stages).filter(stage => stage && stage !== '-')

    // 清空所有槽位
    stageSlots.forEach(slot => {
      config.stages[slot] = '-'
    })

    // 按简化视图的实际显示顺序重新分配
    const sortedStages: string[] = []

    // 1. 先添加自定义关卡（按 custom_stage_1, custom_stage_2, custom_stage_3, custom_stage_4 的顺序）
    for (let i = 1; i <= 4; i++) {
      const key = `custom_stage_${i}` as keyof typeof planData.value.customStageDefinitions
      const stageName = planData.value.customStageDefinitions[key]
      if (stageName && stageName.trim() && enabledStages.includes(stageName)) {
        sortedStages.push(stageName)
      }
    }

    // 2. 再添加标准关卡（按 ALL 缓存的顺序，跳过'-'）
    const allStageOptions = getCachedStageOptions('ALL')
    allStageOptions
      .filter(option => option.value && option.value !== '-')
      .forEach(option => {
        if (enabledStages.includes(option.value!)) {
          sortedStages.push(option.value!)
        }
      })

    // 3. 按顺序分配到槽位：第1个→primary，第2个→backup1，第3个→backup2，第4个→backup3
    sortedStages.forEach((stageName, index) => {
      if (index < stageSlots.length) {
        config.stages[stageSlots[index]] = stageName
      }
    })

    // 只在开发环境输出排序日志
    if (process.env.NODE_ENV === 'development') {
      logger.debug(`关卡排序 ${timeKey}: ${sortedStages.join(' → ')}`)
    }
  }

  // 更新自定义关卡定义
  const updateCustomStageDefinition = (index: 1 | 2 | 3 | 4, name: string) => {
    const key = `custom_stage_${index}` as keyof typeof planData.value.customStageDefinitions
    const oldName = planData.value.customStageDefinitions[key]

    logger.info(`更新自定义关卡-${index}: "${oldName}" -> "${name}"`)

    planData.value.customStageDefinitions[key] = name

    // 如果名称改变了，需要更新所有引用
    if (oldName !== name) {
      dayKeys.value.forEach(timeKey => {
        const config = planData.value.timeConfigs[timeKey]
        Object.keys(config.stages).forEach(stageKey => {
          if (config.stages[stageKey as keyof typeof config.stages] === oldName) {
            config.stages[stageKey as keyof typeof config.stages] = name || '-'
          }
        })
      })
    }
  }

  // 更新计划表ID
  const updatePlanId = (newPlanId: string) => {
    if (currentPlanId.value !== newPlanId) {
      logger.info(`切换: ${currentPlanId.value} -> ${newPlanId}`)
      currentPlanId.value = newPlanId
      // 注意：自定义关卡定义将在 fromApiData 中从后端数据重新推断
    }
  }

  return {
    // 数据
    planData: planData.value,

    // 视图适配器
    configViewData,
    simpleViewData,

    // 数据转换
    fromApiData,
    toApiData,

    // 数据操作
    updateConfig,
    toggleStage,
    updateCustomStageDefinition,
    updatePlanId,

    // 工具函数
    initializeTimeConfigs,
  }
}
