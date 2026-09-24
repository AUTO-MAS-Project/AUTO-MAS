// 活动关跳过簿（MaaUserConfig.Data.ActivitySkipBook）的共享纯逻辑：
// 脚本页用户徽标与计划表活动关指派表共用同一套解析与闸门判定。
// 日期锚点必须与后端 AutoProxy._current_day_marker 一致：东四区日期（与代理统计同锚）。

/** 跳过簿单条目：date=最后一次出错日、days=跨日连错天数、detail=当时指派摘要 */
export interface ActivitySkipEntry {
  date?: string
  days?: number
  detail?: string
}

/** 跳过簿键（活动名）→ 条目 */
export type ActivitySkipBook = Record<string, ActivitySkipEntry>

/** 东四区当日标记（后端闸门与本模块同锚，本地时间要偏移 4 小时） */
export function activityToday(now = Date.now()): string {
  return new Date(now + 4 * 3600_000).toISOString().slice(0, 10)
}

/** 解析用户配置里的跳过簿 JSON；损坏按空簿处理，条目形状不对的丢弃 */
export function parseActivitySkipBook(raw?: string | null): ActivitySkipBook {
  try {
    const parsed: unknown = JSON.parse(raw || '{ }')
    if (!parsed || typeof parsed !== 'object') return {}
    const book: ActivitySkipBook = {}
    for (const [key, entry] of Object.entries(parsed as Record<string, unknown>)) {
      if (entry && typeof entry === 'object') book[key] = entry as ActivitySkipEntry
    }
    return book
  } catch {
    return {}
  }
}

/** 该条目本轮是否命中闸门：首错跳当日（date=今天）或连错≥2 天跳整期 */
function isSkipActive(entry?: ActivitySkipEntry, today = activityToday()): boolean {
  if (!entry) return false
  return (entry.days ?? 0) >= 2 || entry.date === today
}

/** 命中闸门的条目（连错最多的一条；无命中返回 null） */
export function activeSkipEntry(
  book: ActivitySkipBook,
  today = activityToday()
): { name: string; entry: ActivitySkipEntry } | null {
  let hit: { name: string; entry: ActivitySkipEntry } | null = null
  for (const [name, entry] of Object.entries(book)) {
    if (!isSkipActive(entry, today)) continue
    if (!hit || (entry.days ?? 0) > (hit.entry.days ?? 0)) hit = { name, entry }
  }
  return hit
}

/** 条目的展示用摘要（当时指派 + 日期），供 tooltip / 状态列复用 */
export function skipSummary(entry?: ActivitySkipEntry): string {
  if (!entry) return ''
  return [entry.detail, entry.date].filter(Boolean).join(' · ')
}
