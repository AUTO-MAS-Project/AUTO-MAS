import type {
  HSRCapabilitySnapshot,
  HSRTaskCapability,
  HSREngine,
} from '@/composables/useHSRPluginApi'

export interface HSRCapabilityView {
  effectiveEngines: HSREngine[]
  taskKeys: string[]
  supportedModes: string[]
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
  const supportedModes = snapshot?.supported_modes || []

  return {
    effectiveEngines,
    taskKeys,
    supportedModes,
    showSRAFields: effectiveEngines.includes('SRA'),
    showM7AFields: effectiveEngines.includes('M7A'),
    showTaskMapping: taskKeys.length > 0 || supportedModes.includes('managed'),
  }
}

export const resolveCapabilityTaskEngine = (
  snapshot: HSRCapabilitySnapshot | null | undefined,
  taskKey: string,
  fallback: HSREngine = 'SRA'
): HSREngine => {
  const tasks = Array.isArray(snapshot?.tasks)
    ? snapshot.tasks
    : Object.values(snapshot?.tasks || {})
  const task = tasks.find(candidate => candidate.key === taskKey)
  return task?.engines?.[0] || fallback
}
