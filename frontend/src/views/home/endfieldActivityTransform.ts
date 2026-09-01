// 终末地活动数据构建逻辑：与已删除的后端 EndfieldActivityService 一一对应。
// AKEData 源站数据模型变化时只需改本文件（当前为唯一实现）。
// 注意：本文件保持零依赖，便于用 Node 直接做校验（输出结构需与 types/home.ts
// 的 EndfieldActivityOverview 保持一致）。

const AKEDATA_BASE_URL = 'https://data.akedata.wiki'
const AKEDATA_ACTIVITY_IMAGE_PATH =
  'public/images/assets/beyond/dynamicassets/gameplay/ui/sprites/activity'
const AKEDATA_CHARACTER_IMAGE_PATH =
  'public/images/assets/beyond/dynamicassets/gameplay/ui/sprites/charremoteicon'
const POOL_TYPE_NAMES: Record<number, string> = {
  0: '特许寻访',
  1: '新手寻访',
  2: '常驻寻访',
  3: '联合寻访',
}

/** 固定 +08:00 偏移（Asia/Shanghai 无夏令时，与后端 ZoneInfo('Asia/Shanghai') 等价） */
const TIMEZONE_OFFSET_MS = 8 * 60 * 60 * 1000

type TextRef = { id?: string | number } | null | undefined
type NamedRef = { name: TextRef }

interface TimeRangeRecord {
  openTime?: string
  closeTime?: string
}

interface TimeRangeTable {
  [timeId: string]: { timeRangeList?: TimeRangeRecord[] }
}

interface RawActivity {
  name: TextRef
  timeId?: string
  tabImg?: string
  tagIds?: (string | number)[]
  sortId?: number
}

interface RawPool {
  name: TextRef
  type?: number
  clientTopTimeId?: string
  upCharIds?: (string | number)[]
  sortId?: number
}

export interface ResolvedEndfieldActivity {
  activityId: string
  name: string
  startTime: Date | null
  endTime: Date | null
  imageUrl: string
  tags: string[]
  sortId: number
}

export interface ResolvedEndfieldPool {
  poolId: string
  name: string
  poolType: string
  startTime: Date | null
  endTime: Date | null
  imageUrl: string
  upCharacters: string[]
  sortId: number
}

export interface EndfieldSourceData {
  versionId: string
  sourceUpdatedAt: string
  activities: ResolvedEndfieldActivity[]
  pools: ResolvedEndfieldPool[]
}

export interface AkedataManifest {
  latest: string
  updatedAt?: string
  versions?: { id: string; tableCfgPath: string }[]
}

export const AKEDATA_SOURCE_URL = 'https://www.akedata.wiki'

const parseActivityTime = (value: string | null | undefined): Date | null => {
  if (!value) {
    return null
  }
  const parts = value.split(/[/: ]/)
  if (parts.length !== 6) {
    return null
  }
  const year = Number(parts[0])
  const month = Number(parts[1])
  const day = Number(parts[2])
  const hour = Number(parts[3])
  const minute = Number(parts[4])
  const second = Number(parts[5])
  if (
    !Number.isInteger(year) ||
    !Number.isInteger(month) ||
    !Number.isInteger(day) ||
    !Number.isInteger(hour) ||
    !Number.isInteger(minute) ||
    !Number.isInteger(second)
  ) {
    return null
  }
  // 按 +08:00 固定偏移构造，等价于后端 datetime.strptime(...).replace(tzinfo=Asia/Shanghai)
  return new Date(
    Date.UTC(year, month - 1, day, hour, minute, second) - TIMEZONE_OFFSET_MS
  )
}

const formatDateTime = (date: Date): string => {
  const shifted = new Date(date.getTime() + TIMEZONE_OFFSET_MS)
  const pad = (n: number) => String(n).padStart(2, '0')
  // 与后端 datetime.isoformat() 输出一致：2026-09-01T10:00:00+08:00
  const datePart =
    shifted.getUTCFullYear() +
    '-' +
    pad(shifted.getUTCMonth() + 1) +
    '-' +
    pad(shifted.getUTCDate())
  const timePart =
    pad(shifted.getUTCHours()) +
    ':' +
    pad(shifted.getUTCMinutes()) +
    ':' +
    pad(shifted.getUTCSeconds())
  return datePart + 'T' + timePart + '+08:00'
}

/**
 * 64 位整数 id（如 -5316297970819701000）经 JSON.parse 后超出 2^53 精度会失真，
 * 而源站文本/标签/角色表以精确十进制字符串为键（Python 侧 str(int) 保精度可直查）。
 * 此处用 Number 归一化索引回退匹配——引用端与键端经历同一舍入，必然命中；
 * 实测当前数据 140787 键归一化零碰撞，精确键直查优先，归一化仅作回退。
 */
export interface NormalizedLookup<T> {
  get: (id: string | number) => T | undefined
}

export const buildNormalizedLookup = <T,>(table: Record<string, T>): NormalizedLookup<T> => {
  const byNumber = new Map<string, string>()
  for (const key of Object.keys(table)) {
    const normalized = String(Number(key))
    if (!byNumber.has(normalized)) {
      byNumber.set(normalized, key)
    }
  }
  return {
    get: (id: string | number): T | undefined => {
      const key = String(id)
      const exact = table[key]
      if (exact !== undefined) {
        return exact
      }
      const matched = byNumber.get(String(Number(key)))
      return matched !== undefined ? table[matched] : undefined
    },
  }
}

const resolveName = (
  reference: TextRef,
  textLookup: NormalizedLookup<string>,
  fallback: string
): string => {
  const id = reference?.id
  if (id === undefined || id === null) {
    return fallback
  }
  const text = textLookup.get(id)
  return text !== undefined ? text : fallback
}

const firstTimeRange = (
  record: object,
  timeRanges: TimeRangeTable,
  timeKey: string,
  defaultTimeId = ''
): TimeRangeRecord => {
  const timeId =
    (record as Record<string, unknown>)[timeKey] as string | undefined || defaultTimeId
  return timeRanges[timeId]?.timeRangeList?.[0] ?? {}
}

/** 源站表格的宽松输入形态（原始 JSON 由 fetch 得到，具体字段在函数内推断） */
export interface EndfieldTables {
  activities: unknown
  timeRanges: unknown
  activityTags: unknown
  textTable: unknown
  pools: unknown
  characters: unknown
}

export const resolveEndfieldSourceData = (tables: EndfieldTables): Pick<
  EndfieldSourceData,
  'activities' | 'pools'
> => {
  const activitiesTable = tables.activities as Record<string, RawActivity>
  const timeRanges = tables.timeRanges as TimeRangeTable
  const activityTags = tables.activityTags as Record<string, NamedRef>
  const textTable = tables.textTable as Record<string, string>
  const poolsTable = tables.pools as Record<string, RawPool>
  const characters = tables.characters as Record<string, NamedRef>

  const textLookup = buildNormalizedLookup(textTable)
  const tagLookup = buildNormalizedLookup(activityTags)
  const characterLookup = buildNormalizedLookup(characters)

  const activities: ResolvedEndfieldActivity[] = []
  let activityIndex = 0
  for (const [activityId, activity] of Object.entries(activitiesTable)) {
    const timeRange = firstTimeRange(activity, timeRanges, 'timeId')
    const tabImage = activity.tabImg
    const imageUrl = tabImage
      ? AKEDATA_BASE_URL +
        '/' +
        AKEDATA_ACTIVITY_IMAGE_PATH +
        '/' +
        encodeURIComponent(tabImage) +
        '.png'
      : ''
    const tags = (activity.tagIds ?? []).map((tagId) =>
      resolveName(tagLookup.get(tagId)?.name, textLookup, String(tagId))
    )
    activities.push({
      activityId,
      name: resolveName(activity.name, textLookup, activityId),
      startTime: parseActivityTime(timeRange.openTime),
      endTime: parseActivityTime(timeRange.closeTime),
      imageUrl,
      tags,
      sortId: typeof activity.sortId === 'number' ? activity.sortId : activityIndex,
    })
    activityIndex += 1
  }

  const pools: ResolvedEndfieldPool[] = []
  let poolIndex = 0
  for (const [poolId, pool] of Object.entries(poolsTable)) {
    const timeRange = firstTimeRange(pool, timeRanges, 'clientTopTimeId', 'time_' + poolId)
    const upCharacterIds = pool.upCharIds ?? []
    const upCharacters = upCharacterIds.map((characterId) =>
      resolveName(characterLookup.get(characterId)?.name, textLookup, String(characterId))
    )
    const imageUrl = upCharacterIds.length
      ? AKEDATA_BASE_URL +
        '/' +
        AKEDATA_CHARACTER_IMAGE_PATH +
        '/icon_' +
        encodeURIComponent(String(upCharacterIds[0])) +
        '.png'
      : ''
    pools.push({
      poolId,
      name: resolveName(pool.name, textLookup, poolId),
      poolType: pool.type !== undefined ? POOL_TYPE_NAMES[pool.type] ?? '角色寻访' : '角色寻访',
      startTime: parseActivityTime(timeRange.openTime),
      endTime: parseActivityTime(timeRange.closeTime),
      imageUrl,
      upCharacters,
      sortId: typeof pool.sortId === 'number' ? pool.sortId : poolIndex,
    })
    poolIndex += 1
  }

  return { activities, pools }
}

// 与 types/home.ts 的 EndfieldActivityOverview 结构一致（刻意零依赖，便于校验脚本直跑）
export interface EndfieldActivityOverviewLike {
  Available: boolean
  Stale: boolean
  Message: string
  Version: string
  UpdatedAt: string
  SourceName: string
  SourceUrl: string
  Pools: {
    Id: string
    Name: string
    Type: string
    StartTime: string
    EndTime: string
    ImageUrl: string
    UpCharacters: string[]
  }[]
  Activities: {
    Id: string
    Name: string
    StartTime: string
    EndTime: string
    ImageUrl: string
    Tags: string[]
  }[]
}

export const buildEndfieldOverview = (
  source: EndfieldSourceData,
  now: Date
): EndfieldActivityOverviewLike => {
  const isRunning = (startTime: Date | null, endTime: Date | null): boolean =>
    endTime !== null &&
    endTime.getTime() > now.getTime() &&
    (startTime === null || startTime.getTime() <= now.getTime())

  const activePools = source.pools
    .filter((pool) => isRunning(pool.startTime, pool.endTime))
    .sort(
      (a, b) =>
        a.sortId - b.sortId || (a.poolId < b.poolId ? -1 : a.poolId > b.poolId ? 1 : 0)
    )

  const activeActivities = source.activities
    .filter((activity) => isRunning(activity.startTime, activity.endTime))
    .sort(
      (a, b) =>
        a.sortId -
        b.sortId ||
        (a.activityId < b.activityId ? -1 : a.activityId > b.activityId ? 1 : 0)
    )

  return {
    Available: source.versionId !== '',
    Stale: false,
    Message: '',
    Version: source.versionId,
    UpdatedAt: source.sourceUpdatedAt,
    SourceName: 'AKEData',
    SourceUrl: AKEDATA_SOURCE_URL,
    Pools: activePools.map((pool) => ({
      Id: pool.poolId,
      Name: pool.name,
      Type: pool.poolType,
      StartTime: pool.startTime ? formatDateTime(pool.startTime) : '',
      EndTime: pool.endTime ? formatDateTime(pool.endTime) : '',
      ImageUrl: pool.imageUrl,
      UpCharacters: [...pool.upCharacters],
    })),
    Activities: activeActivities.map((activity) => ({
      Id: activity.activityId,
      Name: activity.name,
      StartTime: activity.startTime ? formatDateTime(activity.startTime) : '',
      EndTime: activity.endTime ? formatDateTime(activity.endTime) : '',
      ImageUrl: activity.imageUrl,
      Tags: [...activity.tags],
    })),
  }
}
