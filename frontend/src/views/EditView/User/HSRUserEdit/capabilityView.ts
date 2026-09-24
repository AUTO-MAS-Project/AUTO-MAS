import type {
  HSRCapabilitySnapshot,
  HSRTaskCapability,
  HSREngine,
} from '@/composables/useHSRPluginApi'

interface HSRCapabilityView {
  effectiveEngines: HSREngine[]
  taskKeys: string[]
  showSRAFields: boolean
  showM7AFields: boolean
  showTaskMapping: boolean
}

export const buildHSRCapabilityView = (
  snapshot: HSRCapabilitySnapshot | null | undefined
): HSRCapabilityView => {
  // An explicit empty effective list means paths exist but the native
  // provider is not ready.  Only fall back to configured/candidate engines
  // while the capability snapshot is genuinely unavailable.
  const effectiveEngines = snapshot ? snapshot.effective_engines || [] : []
  const tasks = Array.isArray(snapshot?.tasks)
    ? snapshot.tasks
    : Object.values(snapshot?.tasks || {})
  const taskKeys = tasks.map((task: HSRTaskCapability) => task.key)

  return {
    effectiveEngines,
    taskKeys,
    showSRAFields: effectiveEngines.includes('SRA'),
    showM7AFields: effectiveEngines.includes('M7A'),
    showTaskMapping: taskKeys.length > 0,
  }
}

/**
 * 直控区块要给开关的引擎：当前可选的（云·星穹铁道只有三月七），再加上已勾选但不在
 * 其中的——比如客户端时勾过、切到云平台后仍勾着的 SRA。后端对显式勾选的引擎照样
 * 校验（云平台勾着 SRA 直接拒绝运行），页面不给它的开关，用户就关不掉它。
 */
export const resolveDirectEngineCards = (
  available: readonly HSREngine[],
  control: Partial<Record<HSREngine, boolean | null | undefined>> | null | undefined
): HSREngine[] => {
  const checked = (['SRA', 'M7A'] as const).filter(
    engine => Boolean(control?.[engine]) && !available.includes(engine)
  )
  return [...available, ...checked]
}
