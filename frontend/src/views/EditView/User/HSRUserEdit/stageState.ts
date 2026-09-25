import type {
  HSRPerEngineStageStore,
  HSRScriptStageContainer,
  HSRScriptStagePayload,
  HSRStageEngine,
  HSRUserConfigData,
} from './types'

/**
 * 体力副本在 Stage 里的存取（纯函数，供体力模块设置与模块摘要共用）。
 *
 * 存储结构不变：`Stage.Channel` 是当前要刷的副本类型；`Stage.ScriptStage` 按引擎、
 * 按副本类型各存一项（`{ version: 2, byEngine: { SRA: { engine, stages: { CalyxGolden: … } } } }`），
 * 所以切换副本类型时自然回到该类型之前的选择；`Stage.ScriptEchoOfWar` 按引擎存一项。
 */

export type HSRStageChannel = 'CalyxGolden' | 'CalyxCrimson' | 'Relic' | 'Ornament'

export const STAGE_CHANNELS: readonly HSRStageChannel[] = [
  'CalyxGolden',
  'CalyxCrimson',
  'Relic',
  'Ornament',
]

/** 副本类型 → 引擎动态选项里的分类 key（新旧两种写法都认）。 */
export const CATEGORY_KEYS_BY_CHANNEL: Record<HSRStageChannel, string[]> = {
  CalyxGolden: ['calyx_golden', '拟造花萼（金）'],
  CalyxCrimson: ['calyx_crimson', '拟造花萼（赤）'],
  Relic: ['caver_of_corrosion', '侵蚀隧洞'],
  Ornament: ['ornament_extraction', '饰品提取'],
}

/** 副本类型的显示名词条（组件里再 t()）。 */
export const CHANNEL_LABEL_KEYS: Record<HSRStageChannel, string> = {
  CalyxGolden: 'edit.calyxGolden',
  CalyxCrimson: 'edit.calyxCrimson',
  Relic: 'edit.cavernsCorrosion',
  Ornament: 'edit.ornamentExtraction',
}

export const EOW_WEEKDAY_LABEL_KEYS: Record<string, string> = {
  Monday: 'edit.mon',
  Tuesday: 'edit.tue',
  Wednesday: 'edit.wed',
  Thursday: 'edit.thu',
  Friday: 'edit.fri',
  Saturday: 'edit.sat',
  Sunday: 'edit.sun',
}

export const isEowCategory = (categoryKey: string) =>
  categoryKey === 'echo_of_war' || categoryKey === '历战余响'

type StageData = Pick<HSRUserConfigData['Stage'], 'Channel' | 'ScriptStage' | 'ScriptEchoOfWar'>

export const parseStageObject = (raw: unknown): Record<string, unknown> | null => {
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text || text === '{}' || text === '{ }') return null
    try {
      raw = JSON.parse(text)
    } catch {
      return null
    }
  }
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, unknown>
  }
  return null
}

export const resolveStageChannel = (channel: unknown): HSRStageChannel =>
  STAGE_CHANNELS.includes(channel as HSRStageChannel) ? (channel as HSRStageChannel) : 'CalyxGolden'

/** 读出某引擎名下的那一份（兼容无 byEngine 容器的旧格式）。 */
export const readEngineStage = <T extends HSRScriptStagePayload>(
  raw: unknown,
  engine: HSRStageEngine
): T | null => {
  const root = parseStageObject(raw)
  if (!root) return null

  const byEngine = parseStageObject(root.byEngine)
  if (byEngine) {
    return parseStageObject(byEngine[engine]) as T | null
  }

  if (root.engine === engine) return root as T

  const legacyStages = parseStageObject(root.stages)
  if (legacyStages) {
    const containsEngine = Object.values(legacyStages).some(
      payload => parseStageObject(payload)?.engine === engine
    )
    if (containsEngine) return root as T
  }
  return null
}

/** 把某引擎名下的那一份写回，另一引擎的保持不动；写空时删掉该引擎。 */
export const writeEngineStage = <T extends HSRScriptStagePayload>(
  raw: unknown,
  engine: HSRStageEngine,
  value: T | null
): HSRPerEngineStageStore<T> | Record<string, never> => {
  const root = parseStageObject(raw)
  const existingByEngine = parseStageObject(root?.byEngine)
  const byEngine: Partial<Record<HSRStageEngine, T>> = {}

  if (existingByEngine) {
    for (const item of ['SRA', 'M7A'] as const) {
      const payload = parseStageObject(existingByEngine[item])
      if (payload) byEngine[item] = payload as T
    }
  } else if (root?.engine === 'SRA' || root?.engine === 'M7A') {
    byEngine[root.engine] = root as T
  } else {
    const legacyStages = parseStageObject(root?.stages)
    if (legacyStages) {
      for (const item of ['SRA', 'M7A'] as const) {
        const stages = Object.fromEntries(
          Object.entries(legacyStages).filter(([, payload]) => {
            return parseStageObject(payload)?.engine === item
          })
        )
        if (Object.keys(stages).length) {
          byEngine[item] = { ...root, engine: item, stages } as unknown as T
        }
      }
    }
  }

  if (value) byEngine[engine] = value
  else delete byEngine[engine]

  return Object.keys(byEngine).length ? { version: 2, byEngine } : {}
}

export const readStageContainer = (
  stage: StageData,
  engine: HSRStageEngine
): HSRScriptStageContainer | null => {
  const payload = readEngineStage<HSRScriptStageContainer>(stage.ScriptStage, engine)
  return payload?.stages ? payload : null
}

/** 某引擎下某副本类型保存的那一项；存的是别的引擎的就当没有。 */
export const readChannelStage = (
  stage: StageData,
  engine: HSRStageEngine,
  channel: HSRStageChannel
): HSRScriptStagePayload | null => {
  const payload = readStageContainer(stage, engine)?.stages?.[channel] ?? null
  return payload?.engine === engine ? payload : null
}

export const readEowStage = (
  stage: StageData,
  engine: HSRStageEngine
): HSRScriptStagePayload | null => {
  const payload = readEngineStage<HSRScriptStagePayload>(stage.ScriptEchoOfWar, engine)
  return payload?.engine === engine ? payload : null
}

/** 旧格式（无 byEngine 容器）里存的是另一引擎的副本：需要重选。 */
export const hasLegacyEngineMismatch = (stage: StageData, engine: HSRStageEngine): boolean => {
  const main = parseStageObject(stage.ScriptStage)
  const eow = parseStageObject(stage.ScriptEchoOfWar)
  if (main?.byEngine || eow?.byEngine) return false
  return (!!main?.engine && main.engine !== engine) || (!!eow?.engine && eow.engine !== engine)
}

/**
 * 另一引擎名下已经存了副本，而当前引擎名下一个主副本也没有——刚切换体力模块
 * 执行引擎后的典型状态。
 */
export const isStageMissingForEngine = (stage: StageData, engine: HSRStageEngine): boolean => {
  if (hasLegacyEngineMismatch(stage, engine)) return false
  if (STAGE_CHANNELS.some(channel => readChannelStage(stage, engine, channel) !== null)) {
    return false
  }
  for (const raw of [stage.ScriptStage, stage.ScriptEchoOfWar]) {
    const byEngine = parseStageObject(parseStageObject(raw)?.byEngine)
    if (!byEngine) continue
    for (const other of ['SRA', 'M7A'] as const) {
      if (other !== engine && parseStageObject(byEngine[other])) return true
    }
  }
  return false
}
