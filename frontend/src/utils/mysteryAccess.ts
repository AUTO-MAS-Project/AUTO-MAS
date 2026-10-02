// 每日口令只作轻量门槛，不承担身份认证；日期统一取北京时间。
const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000
const ACCESS_CODE_PATTERN = /^[0-9A-F]{8,64}$/

export function getMysteryDate(date = new Date()): string {
  return new Date(date.getTime() + BEIJING_OFFSET_MS).toISOString().slice(0, 10)
}

export async function getMysteryAccessCode(date = new Date()): Promise<string> {
  const dateString = getMysteryDate(date).replace(/-/g, '')
  const source = new TextEncoder().encode(dateString)
  const digest = await crypto.subtle.digest('SHA-256', source)

  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase()
}

export async function isValidMysteryAccessCode(
  accessCode: string,
  date = new Date()
): Promise<boolean> {
  const candidate = accessCode.trim().toUpperCase()
  if (!ACCESS_CODE_PATTERN.test(candidate)) return false

  return (await getMysteryAccessCode(date)).includes(candidate)
}
