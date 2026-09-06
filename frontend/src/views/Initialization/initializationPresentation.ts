export type InitializationStepKey =
  | 'python'
  | 'pip'
  | 'git'
  | 'repository'
  | 'dependency'
  | 'backend'

export type InitializationStepStatus = 'waiting' | 'processing' | 'success' | 'failed'

export type InitializationStageKey = 'environment' | 'repository' | 'dependency' | 'backend'

export const initializationStages: readonly {
  key: InitializationStageKey
  steps: readonly InitializationStepKey[]
}[] = [
  { key: 'environment', steps: ['python', 'pip', 'git'] },
  { key: 'repository', steps: ['repository'] },
  { key: 'dependency', steps: ['dependency'] },
  { key: 'backend', steps: ['backend'] },
]

export function getInitializationStageKey(stepKey: InitializationStepKey): InitializationStageKey {
  return initializationStages.find(stage => stage.steps.includes(stepKey))?.key ?? 'environment'
}

export function getInitializationStageStatus(
  stageKey: InitializationStageKey,
  stepStatuses: Readonly<Partial<Record<InitializationStepKey, InitializationStepStatus>>>
): InitializationStepStatus {
  const stage = initializationStages.find(item => item.key === stageKey)
  const statuses = stage?.steps.map(step => stepStatuses[step] ?? 'waiting') ?? []

  if (statuses.includes('failed')) return 'failed'
  if (statuses.includes('processing')) return 'processing'
  if (statuses.length > 0 && statuses.every(status => status === 'success')) return 'success'
  return 'waiting'
}

export function formatElapsedSeconds(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(safeSeconds / 60)
  const seconds = safeSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}
