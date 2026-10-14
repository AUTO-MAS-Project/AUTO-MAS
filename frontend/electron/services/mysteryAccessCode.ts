import { createHash } from 'node:crypto'

export interface MysteryAccessContext {
  deviceHash: string
  backendHash: string
}

const HASH_PATTERN = /^[0-9a-f]{64}$/
export const MYSTERY_CODE_PATTERN = /^[A-Za-z0-9_-]{8}$/
export const MYSTERY_CODE_LIFETIME_SECONDS = 1800

export function isMysteryAccessContext(value: unknown): value is MysteryAccessContext {
  return (
    value !== null &&
    typeof value === 'object' &&
    'deviceHash' in value &&
    typeof value.deviceHash === 'string' &&
    HASH_PATTERN.test(value.deviceHash) &&
    'backendHash' in value &&
    typeof value.backendHash === 'string' &&
    HASH_PATTERN.test(value.backendHash)
  )
}

export function generateMysteryAccessCode(context: MysteryAccessContext, issuedAt: number): string {
  const source = `mystery-v1|${context.deviceHash}|${context.backendHash}|${issuedAt}`
  return createHash('sha256').update(source, 'utf8').digest().subarray(0, 6).toString('base64url')
}

/** 只在用户提交时搜索最近 1800 秒；设备与源码指纹由后端缓存。 */
export function verifyMysteryAccessCode(accessCode: unknown, context: unknown): boolean {
  if (typeof accessCode !== 'string' || !isMysteryAccessContext(context)) return false
  const candidate = accessCode.trim()
  if (!MYSTERY_CODE_PATTERN.test(candidate)) return false
  const now = Math.floor(Date.now() / 1000)
  for (let age = 0; age < MYSTERY_CODE_LIFETIME_SECONDS; age++) {
    const issuedAt = now - age
    if (generateMysteryAccessCode(context, issuedAt) === candidate) {
      const checkedAge = Math.floor(Date.now() / 1000) - issuedAt
      return checkedAge >= 0 && checkedAge < MYSTERY_CODE_LIFETIME_SECONDS
    }
  }
  return false
}
