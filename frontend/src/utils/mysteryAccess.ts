// 每日口令只作轻量门槛，不承担身份认证；日期统一取北京时间。
const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000
const ACCESS_CODE_PREFIX = 'AUTO-MAS:mystery:'
const ACCESS_CODE_LENGTH = 8

export function getMysteryDate(date = new Date()): string {
  return new Date(date.getTime() + BEIJING_OFFSET_MS).toISOString().slice(0, 10)
}

export async function getMysteryAccessCode(date = new Date()): Promise<string> {
  const dateString = getMysteryDate(date)
  const source = new TextEncoder().encode(`${ACCESS_CODE_PREFIX}${dateString}`)
  const digest = await crypto.subtle.digest('SHA-256', source)

  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, ACCESS_CODE_LENGTH)
    .toUpperCase()
}
