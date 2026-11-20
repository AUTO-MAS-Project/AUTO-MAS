import type { BannerRegion, BannerWatchOut, CalendarBanner } from '@/api'

export type Region = BannerRegion
export type Banner = CalendarBanner
export type BannerState = BannerWatchOut

export function sameRegion(a: Region, b: Region) {
  return a.game === b.game && a.server === b.server
}
export function shanghai(value: string | null, locale: string, unknown: string) {
  if (!value || !Number.isFinite(Date.parse(value))) return unknown
  return new Intl.DateTimeFormat(locale, {
    timeZone: 'Asia/Shanghai',
    dateStyle: 'medium',
    timeStyle: 'short',
    hourCycle: 'h23',
  }).format(new Date(value))
}
export function opening(
  b: Banner,
  format: (v: string | null) => string,
  label: (key: string) => string
) {
  if (b.confirmed_open_at) return format(b.confirmed_open_at)
  if (b.start_mode === 'after_maintenance') return label('after')
  return b.start_mode === 'scheduled' && b.starts_at ? format(b.starts_at) : label('tbd')
}

type AgentReply = { status: 'ok'; analysis: string } | { status: 'unavailable' | 'failed' | 'busy' }

export async function handoff(
  prompt: string,
  analyze: ((prompt: string) => Promise<AgentReply>) | undefined,
  copy: (prompt: string) => Promise<void>
) {
  try {
    const reply = await analyze?.(prompt)
    if (reply?.status === 'ok') return { message: 'analysis', analysis: reply.analysis }
    if (reply?.status === 'busy') return { message: 'busy' }
  } catch {
    // The host may disconnect while the renderer awaits the reply.
  }
  try {
    await copy(prompt)
    return { message: 'copied' }
  } catch {
    return { message: 'copyFailed' }
  }
}
