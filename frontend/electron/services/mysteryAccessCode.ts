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

const encoder = new TextEncoder()

async function generateMysteryAccessCode(context: MysteryAccessContext, issuedAt: number) {
  const source = `mystery-v1|${context.deviceHash}|${context.backendHash}|${issuedAt}`
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(source))
  return btoa(String.fromCharCode(...new Uint8Array(digest, 0, 6)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
}

/** 只在用户提交时搜索最近 1800 秒；设备与源码指纹由后端缓存。 */
export async function verifyMysteryAccessCode(
  accessCode: unknown,
  context: unknown
): Promise<boolean> {
  if (typeof accessCode !== 'string' || !isMysteryAccessContext(context)) return false
  const candidate = accessCode.trim()
  if (!MYSTERY_CODE_PATTERN.test(candidate)) return false
  const now = Math.floor(Date.now() / 1000)
  for (let age = 0; age < MYSTERY_CODE_LIFETIME_SECONDS; age++) {
    const issuedAt = now - age
    if ((await generateMysteryAccessCode(context, issuedAt)) === candidate) {
      const checkedAge = Math.floor(Date.now() / 1000) - issuedAt
      return checkedAge >= 0 && checkedAge < MYSTERY_CODE_LIFETIME_SECONDS
    }
  }
  return false
}
