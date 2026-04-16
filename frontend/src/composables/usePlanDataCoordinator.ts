/**
 * 璁″垝琛ㄦ暟鎹崗璋冨眰
 *
 * 浣滀负鍓嶇鏋舵瀯涓殑"浜ら€氭寚鎸ヤ腑蹇?锛岃礋璐ｏ細
 * 1. 缁熶竴绠＄悊鏁版嵁娴?
 * 2. 鍗忚皟瑙嗗浘闂寸殑鍚屾
 * 3. 澶勭悊涓庡悗绔殑閫氫俊
 * 4. 鎻愪緵缁熶竴鐨勬暟鎹闂帴鍙?
 */

import { ref, computed } from 'vue'
import {
  STAGE_QUERY_TYPE,
  infoApi,
  type ComboBoxItem,
  type MaaPlanDayRead,
  type MaaPlanRead,
  type StageQueryType,
} from '@/api'
const logger = window.electronAPI.getLogger('璁″垝鏁版嵁鍗忚皟鍣?)

// 鏃堕棿缁村害甯搁噺
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

// 鍏冲崱妲戒綅甯搁噺
export const STAGE_SLOTS = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3'] as const
export type StageSlot = (typeof STAGE_SLOTS)[number]

// 缁熶竴鐨勬暟鎹粨鏋?
export interface PlanDataState {
  // 鍩虹淇℃伅
  info: {
    name: string
    mode: 'ALL' | 'Weekly'
    type: string
  }

  // 鏃堕棿缁村害鐨勯厤缃暟鎹?
  timeConfigs: Record<
    TimeKey,
    {
      medicineNumb: number
      seriesNumb: string
      stages: {
        primary: string // Stage
        backup1: string // Stage_1
        backup2: string // Stage_2
        backup3: string // Stage_3
        remain: string // Stage_Remain
      }
    }
  >

  // 鑷畾涔夊叧鍗″畾涔?
  customStageDefinitions: {
    custom_stage_1: string
    custom_stage_2: string
    custom_stage_3: string
    custom_stage_4: string
  }
}

// 鍏冲崱鍙敤鎬т俊鎭?
export interface StageAvailability {
  value: string
  text: string
  days: number[]
}

// 鏍囧噯鍏冲崱閫夐」缂撳瓨锛堟寜鏃堕棿缁村害锛?
const stageOptionsCache = ref<Record<string, ComboBoxItem[]>>({})

// 鍔犺浇鏍囧噯鍏冲崱閫夐」
export async function loadStageOptions(timeKey: TimeKey): Promise<ComboBoxItem[]> {
  // 濡傛灉宸茬紦瀛橈紝鐩存帴杩斿洖
  if (stageOptionsCache.value[timeKey]) {
    return stageOptionsCache.value[timeKey]
  }

  try {
    // 鏄犲皠鏃堕棿缁村害鍒?API 鍙傛暟
    const typeMap: Record<TimeKey, StageQueryType> = {
      ALL: STAGE_QUERY_TYPE.ALL,
      Monday: STAGE_QUERY_TYPE.MONDAY,
      Tuesday: STAGE_QUERY_TYPE.TUESDAY,
      Wednesday: STAGE_QUERY_TYPE.WEDNESDAY,
      Thursday: STAGE_QUERY_TYPE.THURSDAY,
      Friday: STAGE_QUERY_TYPE.FRIDAY,
      Saturday: STAGE_QUERY_TYPE.SATURDAY,
      Sunday: STAGE_QUERY_TYPE.SUNDAY,
    }

    const response = await infoApi.getStageOptions({
      type: typeMap[timeKey],
    })

    if (response.code === 200 || response.code === undefined) {
      // 缂撳瓨缁撴灉
      stageOptionsCache.value[timeKey] = response.data
      return response.data
    } else {
      logger.error(`鍔犺浇澶辫触 (${timeKey}): ${response.message}`)
      return []
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`鍔犺浇寮傚父 (${timeKey}): ${errorMsg}`)
    return []
  }
}

// 棰勫姞杞芥墍鏈夋椂闂寸淮搴︾殑鍏冲崱閫夐」
export async function preloadAllStageOptions(): Promise<void> {
  const loadPromises = TIME_KEYS.map(timeKey => loadStageOptions(timeKey))
  await Promise.all(loadPromises)
  logger.info('鍏冲崱閫夐」棰勫姞杞藉畬鎴?)
}

// 娓呴櫎缂撳瓨锛堢敤浜庡埛鏂版暟鎹級
export function clearStageOptionsCache(): void {
  stageOptionsCache.value = {}
  logger.info('鍏冲崱閫夐」缂撳瓨宸叉竻闄?)
}

// 鑾峰彇缂撳瓨鐨勫叧鍗￠€夐」
export function getCachedStageOptions(timeKey: TimeKey): ComboBoxItem[] {
  return stageOptionsCache.value[timeKey] || []
}

/**
 * 璁″垝琛ㄦ暟鎹崗璋冨櫒
 */
export function usePlanDataCoordinator() {
  // 褰撳墠璁″垝琛↖D
  const currentPlanId = ref<string>('default')

  const getDefaultCustomStageDefinitions = () => ({
    custom_stage_1: '',
    custom_stage_2: '',
    custom_stage_3: '',
    custom_stage_4: '',
  })

  // 鍗曚竴鏁版嵁婧?
  const planData = ref<PlanDataState>({
    info: {
      name: '',
      mode: 'ALL',
      type: 'MaaPlanConfig',
    },
    timeConfigs: {} as Record<TimeKey, any>,
    customStageDefinitions: getDefaultCustomStageDefinitions(),
  })

  // 鍒濆鍖栨椂闂撮厤缃?
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
          remain: '-',
        },
      }
    })
  }

  // 鍒濆鍖栨暟鎹?
  initializeTimeConfigs()

  // 浠嶢PI鏁版嵁杞崲涓哄唴閮ㄦ暟鎹粨鏋?
  const fromApiData = (apiData: MaaPlanRead, forceUpdateCustomStages = false) => {
    // 鏇存柊鍩虹淇℃伅
    if (apiData.Info) {
      planData.value.info.name = apiData.Info.Name || ''
      planData.value.info.mode = (apiData.Info.Mode as string as 'ALL' | 'Weekly') || 'ALL'

      // 濡傛灉API鏁版嵁涓寘鍚鍒掕〃ID淇℃伅锛屾洿鏂板綋鍓峱lanId
      // 娉ㄦ剰锛氳繖閲屽亣璁緋lanId閫氳繃鍏朵粬鏂瑰紡浼犲叆锛孉PI鏁版嵁鏈韩鍙兘涓嶅寘鍚獻D
    }

    // 鏇存柊鏃堕棿閰嶇疆
    TIME_KEYS.forEach(timeKey => {
      const timeData = apiData[timeKey as keyof MaaPlanRead] as MaaPlanDayRead
      if (timeData) {
        planData.value.timeConfigs[timeKey] = {
          medicineNumb: timeData.MedicineNumb || 0,
          seriesNumb: (timeData.SeriesNumb as string) || '0',
          stages: {
            primary: timeData.Stage || '-',
            backup1: timeData.Stage_1 || '-',
            backup2: timeData.Stage_2 || '-',
            backup3: timeData.Stage_3 || '-',
            remain: timeData.Stage_Remain || '-',
          },
        }
      }
    })

    // 浠庢墍鏈夋椂闂撮厤缃腑鎺ㄦ柇鑷畾涔夊叧鍗″畾涔?
    const inferredStages = new Set<string>()

    TIME_KEYS.forEach(timeKey => {
      const timeData = apiData[timeKey as keyof MaaPlanRead] as MaaPlanDayRead
      if (timeData) {
        // 妫€鏌ユ墍鏈夊叧鍗″瓧娈?
        const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3', 'Stage_Remain'] as const
        stageFields.forEach(field => {
          const stageValue = timeData[field] as string
          if (stageValue && stageValue !== '-') {
            // 濡傛灉涓嶆槸鏍囧噯鍏冲崱锛屽垯璁や负鏄嚜瀹氫箟鍏冲崱
            const cachedOptions = getCachedStageOptions(timeKey)
            const isStandardStage = cachedOptions.some(option => option.value === stageValue)
            if (!isStandardStage) {
              inferredStages.add(stageValue)
            }
          }
        })
      }
    })

    // 鏍规嵁鍙傛暟鍐冲畾鏄惁鏇存柊鑷畾涔夊叧鍗″畾涔?
    if (forceUpdateCustomStages) {
      // 寮哄埗鏇存柊锛氬畬鍏ㄤ粠閰嶇疆鎺ㄦ柇锛堢敤浜庡垵濮嬪姞杞芥垨鍒囨崲璁″垝锛?
      const inferredArray = Array.from(inferredStages).sort()
      planData.value.customStageDefinitions = {
        custom_stage_1: inferredArray[0] || '',
        custom_stage_2: inferredArray[1] || '',
        custom_stage_3: inferredArray[2] || '',
        custom_stage_4: inferredArray[3] || '',
      }

      if (inferredStages.size > 0) {
        logger.info(
          `浠庨厤缃暟鎹帹鏂嚭 ${inferredStages.size} 涓嚜瀹氫箟鍏冲崱: ${Array.from(inferredStages).join(', ')}`
        )
      }
    } else {
      // 鏅鸿兘鍚堝苟锛氫繚鐣欑幇鏈夊畾涔夛紝鍙坊鍔犳柊鍙戠幇鐨勫叧鍗?
      const currentCustomStages = new Set<string>()
      Object.values(planData.value.customStageDefinitions).forEach(stage => {
        if (stage && stage.trim()) {
          currentCustomStages.add(stage)
        }
      })

      // 鎵惧嚭鏂板彂鐜扮殑鍏冲崱锛堝湪鎺ㄦ柇涓絾涓嶅湪褰撳墠瀹氫箟涓級
      const newStages = Array.from(inferredStages).filter(stage => !currentCustomStages.has(stage))

      if (newStages.length > 0) {
        // 灏嗘柊鍏冲崱娣诲姞鍒扮┖鐨勬Ы浣嶄腑
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
        logger.info(`娣诲姞鏂板彂鐜扮殑鑷畾涔夊叧鍗? ${newStages.join(', ')}`)
      }
    }
  }

  // 杞崲涓篈PI鏁版嵁鏍煎紡
  const toApiData = (): MaaPlanRead => {
    const result: MaaPlanRead = {
      Info: {
        Name: planData.value.info.name,
        Mode: planData.value.info.mode as MaaPlanRead['Info'] extends { Mode?: infer M } ? M : never,
      },
    }

    TIME_KEYS.forEach(timeKey => {
      const config = planData.value.timeConfigs[timeKey]
      ;(result as Record<string, unknown>)[timeKey] = {
        MedicineNumb: config.medicineNumb,
        SeriesNumb: config.seriesNumb as MaaPlanDayRead['SeriesNumb'],
        Stage: config.stages.primary,
        Stage_1: config.stages.backup1,
        Stage_2: config.stages.backup2,
        Stage_3: config.stages.backup3,
        Stage_Remain: config.stages.remain,
      }
    })

    // 涓嶄繚瀛樿嚜瀹氫箟鍏冲崱瀹氫箟鍒板悗绔紝瀹冧滑浼氬湪鍔犺浇鏃堕噸鏂版帹鏂?

    return result
  }

  // 閰嶇疆瑙嗗浘鏁版嵁閫傞厤鍣?
  const configViewData = computed(() => {
    return [
      {
        key: 'MedicineNumb',
        taskName: '鍚冪悊鏅鸿嵂',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.medicineNumb || 0,
          ])
        ),
      },
      {
        key: 'SeriesNumb',
        taskName: '杩炴垬娆℃暟',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.seriesNumb || '0',
          ])
        ),
      },
      {
        key: 'Stage',
        taskName: '鍏冲崱閫夋嫨',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.primary || '-',
          ])
        ),
      },
      {
        key: 'Stage_1',
        taskName: '澶囬€夊叧鍗?1',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup1 || '-',
          ])
        ),
      },
      {
        key: 'Stage_2',
        taskName: '澶囬€夊叧鍗?2',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup2 || '-',
          ])
        ),
      },
      {
        key: 'Stage_3',
        taskName: '澶囬€夊叧鍗?3',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.backup3 || '-',
          ])
        ),
      },
      {
        key: 'Stage_Remain',
        taskName: '鍓╀綑鐞嗘櫤鍏冲崱',
        ...Object.fromEntries(
          TIME_KEYS.map(timeKey => [
            timeKey,
            planData.value.timeConfigs[timeKey]?.stages.remain || '-',
          ])
        ),
      },
    ]
  })

  // 绠€鍖栬鍥炬暟鎹€傞厤鍣?
  const simpleViewData = computed(() => {
    const result: any[] = []

    // 娣诲姞鑷畾涔夊叧鍗?
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
          ...stageStates,
        })
      }
    })

    // 娣诲姞鏍囧噯鍏冲崱锛堜粠 ALL 鐨勭紦瀛樹腑鑾峰彇鎵€鏈夋爣鍑嗗叧鍗★級
    const allStageOptions = getCachedStageOptions('ALL')
    allStageOptions
      .filter(option => option.value && option.value !== '-')
      .forEach(option => {
        const stageStates: Record<string, boolean> = {}
        TIME_KEYS.forEach(timeKey => {
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

  // 鏇存柊閰嶇疆鏁版嵁
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

  // 鍒囨崲鍏冲崱鐘舵€侊紙绠€鍖栬鍥剧敤锛?
  const toggleStage = (stageName: string, timeKey: TimeKey, enabled: boolean) => {
    const config = planData.value.timeConfigs[timeKey]
    const stageSlots = ['primary', 'backup1', 'backup2', 'backup3'] as const

    if (enabled) {
      // 鎵惧埌绗竴涓┖妲戒綅
      const emptySlot = stageSlots.find(slot => !config.stages[slot] || config.stages[slot] === '-')
      if (emptySlot) {
        config.stages[emptySlot] = stageName
      }
      // 鍚敤鍚庨噸鏂版寜绠€鍖栬鍥鹃『搴忔帓鍒?
      reassignSlotsBySimpleViewOrder(timeKey)
    } else {
      // 浠庢墍鏈夋Ы浣嶄腑绉婚櫎
      stageSlots.forEach(slot => {
        if (config.stages[slot] === stageName) {
          config.stages[slot] = '-'
        }
      })
      // 绉婚櫎鍚庨噸鏂版寜绠€鍖栬鍥鹃『搴忔帓鍒?
      reassignSlotsBySimpleViewOrder(timeKey)
    }
  }

  // 鎸夌畝鍖栬鍥鹃『搴忛噸鏂板垎閰嶆Ы浣?
  const reassignSlotsBySimpleViewOrder = (timeKey: TimeKey) => {
    const config = planData.value.timeConfigs[timeKey]
    const stageSlots = ['primary', 'backup1', 'backup2', 'backup3'] as const

    // 鏀堕泦褰撳墠宸插惎鐢ㄧ殑鍏冲崱
    const enabledStages = Object.values(config.stages).filter(stage => stage && stage !== '-')

    // 娓呯┖鎵€鏈夋Ы浣?
    stageSlots.forEach(slot => {
      config.stages[slot] = '-'
    })

    // 鎸夌畝鍖栬鍥剧殑瀹為檯鏄剧ず椤哄簭閲嶆柊鍒嗛厤
    const sortedStages: string[] = []

    // 1. 鍏堟坊鍔犺嚜瀹氫箟鍏冲崱锛堟寜 custom_stage_1, custom_stage_2, custom_stage_3, custom_stage_4 鐨勯『搴忥級
    for (let i = 1; i <= 4; i++) {
      const key = `custom_stage_${i}` as keyof typeof planData.value.customStageDefinitions
      const stageName = planData.value.customStageDefinitions[key]
      if (stageName && stageName.trim() && enabledStages.includes(stageName)) {
        sortedStages.push(stageName)
      }
    }

    // 2. 鍐嶆坊鍔犳爣鍑嗗叧鍗★紙鎸?ALL 缂撳瓨鐨勯『搴忥紝璺宠繃'-'锛?
    const allStageOptions = getCachedStageOptions('ALL')
    allStageOptions
      .filter(option => option.value && option.value !== '-')
      .forEach(option => {
        if (enabledStages.includes(option.value!)) {
          sortedStages.push(option.value!)
        }
      })

    // 3. 鎸夐『搴忓垎閰嶅埌妲戒綅锛氱1涓啋primary锛岀2涓啋backup1锛岀3涓啋backup2锛岀4涓啋backup3
    sortedStages.forEach((stageName, index) => {
      if (index < stageSlots.length) {
        config.stages[stageSlots[index]] = stageName
      }
    })

    // 鍙湪寮€鍙戠幆澧冭緭鍑烘帓搴忔棩蹇?
    if (process.env.NODE_ENV === 'development') {
      logger.debug(`鍏冲崱鎺掑簭 ${timeKey}: ${sortedStages.join(' 鈫?')}`)
    }
  }

  // 鏇存柊鑷畾涔夊叧鍗″畾涔?
  const updateCustomStageDefinition = (index: 1 | 2 | 3 | 4, name: string) => {
    const key = `custom_stage_${index}` as keyof typeof planData.value.customStageDefinitions
    const oldName = planData.value.customStageDefinitions[key]

    logger.info(`鏇存柊鑷畾涔夊叧鍗?${index}: "${oldName}" -> "${name}"`)

    planData.value.customStageDefinitions[key] = name

    // 濡傛灉鍚嶇О鏀瑰彉浜嗭紝闇€瑕佹洿鏂版墍鏈夊紩鐢?
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

  // 鏇存柊璁″垝琛↖D
  const updatePlanId = (newPlanId: string) => {
    if (currentPlanId.value !== newPlanId) {
      logger.info(`鍒囨崲: ${currentPlanId.value} -> ${newPlanId}`)
      currentPlanId.value = newPlanId
      // 娉ㄦ剰锛氳嚜瀹氫箟鍏冲崱瀹氫箟灏嗗湪 fromApiData 涓粠鍚庣鏁版嵁閲嶆柊鎺ㄦ柇
    }
  }

  return {
    // 鏁版嵁
    planData: planData.value,

    // 瑙嗗浘閫傞厤鍣?
    configViewData,
    simpleViewData,

    // 鏁版嵁杞崲
    fromApiData,
    toApiData,

    // 鏁版嵁鎿嶄綔
    updateConfig,
    toggleStage,
    updateCustomStageDefinition,
    updatePlanId,

    // 宸ュ叿鍑芥暟
    initializeTimeConfigs,
  }
}

