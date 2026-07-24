export const ELEVATION_HANDOFF_ARGUMENT = '--auto-mas-elevation-handoff='

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu

export function readElevationHandoffToken(commandLine: readonly string[]): string | null {
  const argument = commandLine.find(value => value.startsWith(ELEVATION_HANDOFF_ARGUMENT))
  const token = argument?.slice(ELEVATION_HANDOFF_ARGUMENT.length) || ''
  return UUID_PATTERN.test(token) ? token : null
}

export function buildElevationHandoffArguments(
  commandLine: readonly string[],
  handoffToken: string
): string[] {
  if (!UUID_PATTERN.test(handoffToken)) {
    throw new Error('Elevation handoff requires a UUID token')
  }
  return [
    ...commandLine.filter(argument => !argument.startsWith(ELEVATION_HANDOFF_ARGUMENT)),
    `${ELEVATION_HANDOFF_ARGUMENT}${handoffToken}`,
  ]
}

export interface SingleInstanceLockOptions {
  commandLine: readonly string[]
  requestLock: (additionalData?: Record<string, unknown>) => boolean
  timeoutMs: number
  retryIntervalMs?: number
  delay?: (milliseconds: number) => Promise<void>
  now?: () => number
}

/** Let an elevated successor wait while the verified old instance performs cleanup. */
export async function waitForSingleInstanceLock({
  commandLine,
  requestLock,
  timeoutMs,
  retryIntervalMs = 100,
  delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)),
  now = Date.now,
}: SingleInstanceLockOptions): Promise<boolean> {
  const handoffToken = readElevationHandoffToken(commandLine)
  const additionalData = handoffToken ? { elevationHandoffToken: handoffToken } : undefined
  if (requestLock(additionalData)) {
    return true
  }
  if (!handoffToken) {
    return false
  }

  const deadline = now() + timeoutMs
  while (now() < deadline) {
    await delay(retryIntervalMs)
    if (requestLock(additionalData)) {
      return true
    }
  }
  return false
}

/** Never expose the single-instance lock until old-instance cleanup has settled. */
export async function completeElevationHandoff(
  cleanup: () => Promise<void>,
  releaseLock: () => void,
  quit: () => void
): Promise<void> {
  await cleanup()
  releaseLock()
  quit()
}
