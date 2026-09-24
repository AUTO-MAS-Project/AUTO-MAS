// 活动关跳过簿（MaaUserConfig.Data.ActivitySkipBook）的共享纯逻辑：
// 脚本页用户徽标与计划表活动关指派表共用同一套解析与闸门判定。
// 日期锚点必须与后端 AutoProxy._current_day_marker 一致：东四区日期（与代理统计同锚）。

/** 跳过簿单条目：date=最后一次出错日、days=连错天数（打成功即清零，仅供提示）、detail=当时指派摘要 */
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

/** 该条目本轮是否命中闸门：只在出错当天拦住，次日自动重试（与后端同判据） */
function isSkipActive(entry?: ActivitySkipEntry, today = activityToday()): boolean {
  if (!entry) return false
  return entry.date === today
}

/** 命中闸门的条目（当日出错的那些里取连错最多的一条；无命中返回 null） */
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

/**
 * 只保留「该活动仍在该服进行中」的条目。跳过簿按活动名归属，对不上的是上期遗留
 *（后端要等下一轮运行才修剪），脚本页徽标与计划表指派表都先用它过滤；没有该服
 * 当期数据（未加载或拉取失败）时视为没有进行中活动，两处口径一致。
 */
export function ongoingSkipBook(
  book: ActivitySkipBook,
  ongoingNames: Set<string> | undefined
): ActivitySkipBook {
  const kept: ActivitySkipBook = {}
  if (!ongoingNames) return kept
  for (const [name, entry] of Object.entries(book)) {
    if (ongoingNames.has(name)) kept[name] = entry
  }
  return kept
}

/** 条目的展示用摘要（当时指派 + 日期），供 tooltip / 状态列复用 */
export function skipSummary(entry?: ActivitySkipEntry): string {
  if (!entry) return ''
  return [entry.detail, entry.date].filter(Boolean).join(' · ')
}
