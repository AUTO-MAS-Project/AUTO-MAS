import type {
  HSREngine,
  HSRCapabilitySnapshot,
  HSRTaskCapability,
} from '@/composables/useHSRPluginApi'

export interface HSRCapabilityView {
  available: boolean
  effectiveEngines: Set<HSREngine>
  taskKeys: Set<string>
  supportedModes: Set<string>
  showSRAFields: boolean
  showM7AFields: boolean
  showTaskMapping: boolean
}

export const buildHSRCapabilityView = (
  snapshot: HSRCapabilitySnapshot | null | undefined
): HSRCapabilityView => {
  const effectiveEngines = new Set<HSREngine>(snapshot?.effective_engines || [])
  const taskKeys = new Set(
    (snapshot?.tasks || [])
      .filter(task => task.engines.some(engine => effectiveEngines.has(engine)))
      .map(task => task.key)
  )
  return {
    available: snapshot?.available === true && effectiveEngines.size > 0,
    effectiveEngines,
    taskKeys,
    supportedModes: new Set(snapshot?.supported_modes || []),
    showSRAFields: effectiveEngines.has('SRA'),
    showM7AFields: effectiveEngines.has('M7A'),
    showTaskMapping: effectiveEngines.size > 1,
  }
}

export const resolveCapabilityTaskEngine = (
  snapshot: HSRCapabilitySnapshot | null | undefined,
  taskKey: string,
  configuredEngine?: HSREngine
): HSREngine | undefined => {
  const view = buildHSRCapabilityView(snapshot)
  const task: HSRTaskCapability | undefined = snapshot?.tasks.find(item => item.key === taskKey)
  if (!task) return undefined

  const effectiveTaskEngines = task.engines.filter(engine => view.effectiveEngines.has(engine))
  if (effectiveTaskEngines.length === 1) return effectiveTaskEngines[0]
  if (configuredEngine && effectiveTaskEngines.includes(configuredEngine)) return configuredEngine
  return effectiveTaskEngines[0]
}
