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
import type { MaaPlanConfig, MaaPlanConfig_Item } from '@/api'

// 时间维度常量
export const TIME_KEYS = ['ALL', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const
export type TimeKey = typeof TIME_KEYS[number]

// 关卡槽位常量
export const STAGE_SLOTS = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3'] as const
export type StageSlot = typeof STAGE_SLOTS[number]

// 统一的数据结构
export interface PlanDataState {
  // 基础信息
  info: {
    name: string
    mode: 'ALL' | 'Weekly'
    type: string
  }
  
  // 时间维度的配置数据
  timeConfigs: Record<TimeKey, {
    medicineNumb: number
    seriesNumb: string
    stages: {
      primary: string      // Stage
      backup1: string      // Stage_1
      backup2: string      // Stage_2
      backup3: string      // Stage_3
      remain: string       // Stage_Remain
    }
  }>
  
  // 自定义关卡定义
  customStageDefinitions: {
    custom_stage_1: string
    custom_stage_2: string
    custom_stage_3: string
  }
}

// 关卡可用性信息
export interface StageAvailability {
  value: string
  text: string
  days: number[]
}

export const STAGE_DAILY_INFO: StageAvailability[] = [
  { value: '-', text: '当前/上次', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: '1-7', text: '1-7', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'R8-11', text: 'R8-11', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: '12-17-HARD', text: '12-17-HARD', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'LS-6', text: '经验-6/5', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'CE-6', text: '龙门币-6/5', days: [2, 4, 6, 7] },
  { value: 'AP-5', text: '红票-5', days: [1, 4, 6, 7] },
  { value: 'CA-5', text: '技能-5', days: [2, 3, 5, 7] },
  { value: 'SK-5', text: '碳-5', days: [1, 3, 5, 6] },
  { value: 'PR-A-1', text: '奶/盾芯片', days: [1, 4, 5, 7] },
  { value: 'PR-A-2', text: '奶/盾芯片组', days: [1, 4, 5, 7] },
  { value: 'PR-B-1', text: '术/狙芯片', days: [1, 2, 5, 6] },
  { value: 'PR-B-2', text: '术/狙芯片组', days: [1, 2, 5, 6] },
  { value: 'PR-C-1', text: '先/辅芯片', days: [3, 4, 6, 7] },
  { value: 'PR-C-2', text: '先/辅芯片组', days: [3, 4, 6, 7] },
  { value: 'PR-D-1', text: '近/特芯片', days: [2, 3, 6, 7] },
  { value: 'PR-D-2', text: '近/特芯片组', days: [2, 3, 6, 7] },
]

/**
 * 计划表数据协调器
 */
export function usePlanDataCoordinator() {
  // 当前计划表ID
  const currentPlanId = ref<string>('default')
  
  // localStorage 相关函数
  const CUSTOM_STAGE_KEY_PREFIX = 'maa_custom_stage_definitions_'
  
  const getStorageKey = (): string => {
    return `${CUSTOM_STAGE_KEY_PREFIX}${currentPlanId.value}`
  }
  
  const getDefaultCustomStageDefinitions = () => ({
    custom_stage_1: '',
    custom_stage_2: '',
    custom_stage_3: '',
  })

  const loadCustomStageDefinitionsFromStorage = () => {
    try {
      const storageKey = getStorageKey()
      const stored = localStorage.getItem(storageKey)
      if (stored) {
        const parsed = JSON.parse(stored)
        // 确保包含所有必需的键
        return {
          custom_stage_1: parsed.custom_stage_1 || '',
          custom_stage_2: parsed.custom_stage_2 || '',
          custom_stage_3: parsed.custom_stage_3 || '',
        }
      }
    } catch (error) {
      console.error('[自定义关卡] localStorage 恢复失败:', error)
    }
    
    return getDefaultCustomStageDefinitions()
  }
  
  const saveCustomStageDefinitionsToStorage = (definitions: Record<string, string>) => {
    try {
      const storageKey = getStorageKey()
      localStorage.setItem(storageKey, JSON.stringify(definitions))
      // 只在开发环境输出详细日志
      if (process.env.NODE_ENV === 'development') {
        console.log(`[自定义关卡] 保存到 localStorage (${currentPlanId.value})`)
      }
    } catch (error) {
      console.error('[自定义关卡] localStorage 保存失败:', error)
    }
  }

  // 单一数据源
  const planData = ref<PlanDataState>({
    info: {
      name: '',
      mode: 'ALL',
      type: 'MaaPlanConfig'
    },
    timeConfigs: {} as Record<TimeKey, any>,
    customStageDefinitions: loadCustomStageDefinitionsFromStorage()
  })

  // 初始化时间配置
  const initializeTimeConfigs = () => {
    TIME_KEYS.forEach(timeKey => {
      planData.value.timeConfigs[timeKey] = {
        medicineNumb: 0,
        seriesNumb: '0',
        stages: {
          primary: '-',
          backup1: '-',
          backup2: '-',
          backup3: '-',
          remain: '-'
        }
      }
    })
  }

  // 初始化数据
  initializeTimeConfigs()

  // 从API数据转换为内部数据结构
  const fromApiData = (apiData: MaaPlanConfig) => {
    // 更新基础信息
    if (apiData.Info) {
      planData.value.info.name = apiData.Info.Name || ''
      planData.value.info.mode = apiData.Info.Mode || 'ALL'
      
      // 如果API数据中包含计划表ID信息，更新当前planId
      // 注意：这里假设planId通过其他方式传入，API数据本身可能不包含ID
    }

    // 更新时间配置
    TIME_KEYS.forEach(timeKey => {
      const timeData = apiData[timeKey] as MaaPlanConfig_Item
      if (timeData) {
        planData.value.timeConfigs[timeKey] = {
          medicineNumb: timeData.MedicineNumb || 0,
          seriesNumb: timeData.SeriesNumb || '0',
          stages: {
            primary: timeData.Stage || '-',
            backup1: timeData.Stage_1 || '-',
            backup2: timeData.Stage_2 || '-',
            backup3: timeData.Stage_3 || '-',
            remain: timeData.Stage_Remain || '-'
          }
        }
      }
    })

    // 更新自定义关卡定义
    const customStages = (apiData.ALL as any)?.customStageDefinitions
    if (customStages && typeof customStages === 'object') {
      // 只在开发环境输出详细日志
      if (process.env.NODE_ENV === 'development') {
        console.log(`[自定义关卡] 从后端数据恢复 (${currentPlanId.value})`)
      }
      const newDefinitions = {
        custom_stage_1: customStages.custom_stage_1 || '',
        custom_stage_2: customStages.custom_stage_2 || '',
        custom_stage_3: customStages.custom_stage_3 || '',
      }
      
      // 只有当定义真的不同时才更新和保存
      const hasChanged = JSON.stringify(newDefinitions) !== JSON.stringify(planData.value.customStageDefinitions)
      
      if (hasChanged) {
        planData.value.customStageDefinitions = newDefinitions
        // 同步到 localStorage
        saveCustomStageDefinitionsToStorage(planData.value.customStageDefinitions)
      }
    } else {
      // 只在开发环境输出日志
      if (process.env.NODE_ENV === 'development') {
        console.log(`[自定义关卡] 使用 localStorage 数据 (${currentPlanId.value})`)
      }
      // 如果后端没有自定义关卡定义，使用 localStorage 中的值
      const storedDefinitions = loadCustomStageDefinitionsFromStorage()
      planData.value.customStageDefinitions = storedDefinitions
    }
  }

  // 转换为API数据格式
  const toApiData = (): MaaPlanConfig => {
    const result: MaaPlanConfig = {
      Info: {
        Name: planData.value.info.name,
        Mode: planData.value.info.mode
      }
    }

    TIME_KEYS.forEach(timeKey => {
      const config = planData.value.timeConfigs[timeKey]
      result[timeKey] = {
        MedicineNumb: config.medicineNumb,
        SeriesNumb: config.seriesNumb as any,
        Stage: config.stages.primary,
        Stage_1: config.stages.backup1,
        Stage_2: config.stages.backup2,
        Stage_3: config.stages.backup3,
        Stage_Remain: config.stages.remain
      }
    })

    // 在ALL中包含自定义关卡定义
    if (result.ALL) {
      (result.ALL as any).customStageDefinitions = planData.value.customStageDefinitions
    }

    return result
  }

  // 配置视图数据适配器
  const configViewData = computed(() => {
    return [
      {
        key: 'MedicineNumb',
        taskName: '吃理智药',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.medicineNumb || 0
          ])
        )
      },
      {
        key: 'SeriesNumb',
        taskName: '连战次数',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.seriesNumb || '0'
          ])
        )
      },
      {
        key: 'Stage',
        taskName: '关卡选择',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.primary || '-'
          ])
        )
      },
      {
        key: 'Stage_1',
        taskName: '备选关卡-1',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup1 || '-'
          ])
        )
      },
      {
        key: 'Stage_2',
        taskName: '备选关卡-2',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup2 || '-'
          ])
        )
      },
      {
        key: 'Stage_3',
        taskName: '备选关卡-3',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup3 || '-'
          ])
        )
      },
      {
        key: 'Stage_Remain',
        taskName: '剩余理智关卡',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.remain || '-'
          ])
        )
      }
    ]
  })

  // 简化视图数据适配器
  const simpleViewData = computed(() => {
    const result: any[] = []

    // 添加自定义关卡
    Object.entries(planData.value.customStageDefinitions).forEach(([, stageName]) => {
      if (stageName && stageName.trim()) {
        const stageStates: Record<string, boolean> = {}
        TIME_KEYS.forEach(timeKey => {
          const config = planData.value.timeConfigs[timeKey]
          stageStates[timeKey] = Object.values(config.stages).includes(stageName)
        })

        result.push({
          key: stageName,
          taskName: stageName,
          isCustom: true,
          stageName: stageName,
          ...stageStates
        })
      }
    })

    // 添加标准关卡
    STAGE_DAILY_INFO.filter(stage => stage.value !== '-').forEach(stage => {
      const stageStates: Record<string, boolean> = {}
      TIME_KEYS.forEach(timeKey => {
        const config = planData.value.timeConfigs[timeKey]
        stageStates[timeKey] = Object.values(config.stages).includes(stage.value)
      })

      result.push({
        key: stage.value,
        taskName: stage.text,
        isCustom: false,
        stageName: stage.value,
        ...stageStates
      })
    })

    return result
  })

  // 更新配置数据
  const updateConfig = (timeKey: TimeKey, field: string, value: any) => {
    if (field === 'MedicineNumb') {
      planData.value.timeConfigs[timeKey].medicineNumb = value
    } else if (field === 'SeriesNumb') {
      planData.value.timeConfigs[timeKey].seriesNumb = value
    } else if (field === 'Stage') {
      planData.value.timeConfigs[timeKey].stages.primary = value
    } else if (field === 'Stage_1') {
      planData.value.timeConfigs[timeKey].stages.backup1 = value
    } else if (field === 'Stage_2') {
      planData.value.timeConfigs[timeKey].stages.backup2 = value
    } else if (field === 'Stage_3') {
      planData.value.timeConfigs[timeKey].stages.backup3 = value
    } else if (field === 'Stage_Remain') {
      planData.value.timeConfigs[timeKey].stages.remain = value
    }
  }

  // 切换关卡状态（简化视图用）
  const toggleStage = (stageName: string, timeKey: TimeKey, enabled: boolean) => {
    const config = planData.value.timeConfigs[timeKey]
    const stageSlots = ['primary', 'backup1', 'backup2', 'backup3'] as const

    if (enabled) {
      // 找到第一个空槽位
      const emptySlot = stageSlots.find(slot => 
        !config.stages[slot] || config.stages[slot] === '-'
      )
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
  const reassignSlotsBySimpleViewOrder = (timeKey: TimeKey) => {
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
    
    // 1. 先添加自定义关卡（按 custom_stage_1, custom_stage_2, custom_stage_3 的顺序）
    for (let i = 1; i <= 3; i++) {
      const key = `custom_stage_${i}` as keyof typeof planData.value.customStageDefinitions
      const stageName = planData.value.customStageDefinitions[key]
      if (stageName && stageName.trim() && enabledStages.includes(stageName)) {
        sortedStages.push(stageName)
      }
    }
    
    // 2. 再添加标准关卡（按STAGE_DAILY_INFO的顺序，跳过'-'）
    STAGE_DAILY_INFO.filter(stage => stage.value !== '-').forEach(stage => {
      if (enabledStages.includes(stage.value)) {
        sortedStages.push(stage.value)
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
      console.log(`[关卡排序] ${timeKey}:`, sortedStages.join(' → '))
    }
  }



  // 更新自定义关卡定义
  const updateCustomStageDefinition = (index: 1 | 2 | 3, name: string) => {
    const key = `custom_stage_${index}` as keyof typeof planData.value.customStageDefinitions
    const oldName = planData.value.customStageDefinitions[key]
    
    // 只在开发环境输出详细日志
    if (process.env.NODE_ENV === 'development') {
      console.log(`[自定义关卡] 保存关卡-${index}: "${oldName}" -> "${name}"`)
    }
    
    planData.value.customStageDefinitions[key] = name
    
    // 保存到 localStorage
    saveCustomStageDefinitionsToStorage(planData.value.customStageDefinitions)

    // 如果名称改变了，需要更新所有引用
    if (oldName !== name) {
      TIME_KEYS.forEach(timeKey => {
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
      // 只在开发环境输出日志
      if (process.env.NODE_ENV === 'development') {
        console.log(`[自定义关卡] 计划表切换: ${currentPlanId.value} -> ${newPlanId}`)
      }

      currentPlanId.value = newPlanId
      
      // 重新加载自定义关卡定义
      const newDefinitions = loadCustomStageDefinitionsFromStorage()
      planData.value.customStageDefinitions = newDefinitions
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
    initializeTimeConfigs
  }
}