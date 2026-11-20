export const OUTPUT_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
export type OutputLogLevel = (typeof OUTPUT_LOG_LEVELS)[number]

export function normalizeOutputLogLevel(value: unknown): OutputLogLevel {
  return OUTPUT_LOG_LEVELS.find(level => level === value) ?? 'INFO'
}
