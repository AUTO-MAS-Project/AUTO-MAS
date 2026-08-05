const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}

const asText = (value: unknown) => (typeof value === 'string' ? value.trim() : '')

const normalizeProjectName = (value: unknown) => {
  let name = asText(value)
  if (!name) return ''

  name = name.split('@', 1)[0].trim()
  name = name
    .replace(/\s*[-_·]?\s*(?:版本号\s*[:：]?\s*)?v?\d+(?:\.\d+)+(?:[-+][\w.]+)?$/i, '')
    .trim()

  const duplicateParts = name.split(/\s*[-–—]\s*/)
  if (duplicateParts.length === 2 && duplicateParts[0] === duplicateParts[1]) {
    return duplicateParts[0]
  }
  return name
}

export const isMaaFWProjectType = (type: unknown) =>
  type === 'MaaFW' || type === 'MaaFWManaged' || type === 'M9A'

export const getMaaFWProjectLabel = (script: unknown) => {
  const record = asRecord(script)
  const config = asRecord(record.config)
  const info = asRecord(config.Info)
  const managed = asRecord(config.Managed)
  const project = asRecord(config.Project)

  const candidates = [
    info.ProjectLabel,
    info.Name,
    managed.ProjectId,
    managed.projectId,
    project.ProjectId,
    project.projectId,
    config.ProjectId,
    config.projectId,
  ]
  for (const candidate of candidates) {
    const label = normalizeProjectName(candidate)
    if (label) return label
  }
  return 'MFW 项目'
}
