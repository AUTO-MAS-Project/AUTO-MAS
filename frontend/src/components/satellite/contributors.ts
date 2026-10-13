/**
 * 开发者本周 commit 打榜：从 GitHub 公开接口拉 AUTO-MAS dev 分支本周一 0 点以来的提交，
 * 按作者数一数。只在彩蛋触发时请求，平时不联网。
 */

const COMMITS_URL = 'https://api.github.com/repos/AUTO-MAS-Project/AUTO-MAS/commits'
const PAGE_SIZE = 100
/** 一周的提交翻到这么多页就停：dev 一天十几到几十个提交，五页够一周用 */
const MAX_PAGES = 5
const FETCH_TIMEOUT_MS = 6000
/** 5 分钟内重复触发就用上次的结果，免得撞 GitHub 未登录每小时 60 次的限额 */
const CACHE_MS = 5 * 60 * 1000

export interface Contributor {
  login: string
  /** 提交没关联到 GitHub 账号时为空，榜单上显示名字首字 */
  avatarUrl: string
  commits: number
}

export interface WeeklyBoard {
  /** 本周一 0 点（本地时间） */
  since: Date
  list: Contributor[]
}

/** 本周一 0 点（本地时间） */
export function startOfWeek(now: Date): Date {
  const monday = new Date(now)
  monday.setHours(0, 0, 0, 0)
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7))
  return monday
}

/**
 * 把 commits 接口的若干页结果按作者数一数：合并提交不算，机器人不算；
 * 没关联 GitHub 账号的按提交里写的名字算。按提交数从多到少排。
 */
export function tallyCommits(pages: readonly unknown[]): Contributor[] {
  const byLogin = new Map<string, Contributor>()

  for (const page of pages) {
    if (!Array.isArray(page)) continue
    for (const item of page) {
      if (typeof item !== 'object' || item === null) continue
      const { author, commit, parents } = item as Record<string, unknown>
      if (Array.isArray(parents) && parents.length > 1) continue

      const account = (typeof author === 'object' && author !== null ? author : {}) as Record<
        string,
        unknown
      >
      if (account.type === 'Bot' || String(account.login ?? '').endsWith('[bot]')) continue

      const commitAuthor = (commit as { author?: { name?: unknown } } | undefined)?.author
      const login =
        typeof account.login === 'string'
          ? account.login
          : typeof commitAuthor?.name === 'string'
            ? commitAuthor.name
            : null
      if (!login) continue

      const entry = byLogin.get(login) ?? {
        login,
        avatarUrl: typeof account.avatar_url === 'string' ? account.avatar_url : '',
        commits: 0,
      }
      entry.commits += 1
      byLogin.set(login, entry)
    }
  }

  return [...byLogin.values()].sort((left, right) => right.commits - left.commits)
}

let cache: { at: number; board: WeeklyBoard } | null = null

async function fetchPage(since: Date, page: number): Promise<unknown[]> {
  const url = `${COMMITS_URL}?sha=dev&since=${since.toISOString()}&per_page=${PAGE_SIZE}&page=${page}`
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const response = await fetch(url, {
      headers: { Accept: 'application/vnd.github+json' },
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new Error(`GitHub 返回 ${response.status}`)
    }
    const body: unknown = await response.json()
    return Array.isArray(body) ? body : []
  } finally {
    window.clearTimeout(timer)
  }
}

/** 拉本周的提交榜；网络不通、超时或限流时抛错，由调用方显示「火箭没油了」 */
export async function fetchWeeklyBoard(): Promise<WeeklyBoard> {
  if (cache && Date.now() - cache.at < CACHE_MS) {
    return cache.board
  }

  const since = startOfWeek(new Date())
  const pages: unknown[][] = []
  for (let page = 1; page <= MAX_PAGES; page++) {
    const items = await fetchPage(since, page)
    pages.push(items)
    if (items.length < PAGE_SIZE) break
  }

  const board = { since, list: tallyCommits(pages) }
  cache = { at: Date.now(), board }
  return board
}

/** 头像要个小尺寸的就够了 */
export function sizedAvatar(url: string, size: number): string {
  return `${url}${url.includes('?') ? '&' : '?'}s=${size}`
}
