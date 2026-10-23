import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Composer } from 'vue-i18n'
import { GameCalendarActivityCompletionIn } from '@/api'
import {
  useActivityCompletionApi,
  type ActivityCompletionScope,
} from '@/composables/useActivityCompletionApi'
import { HOME_ACTIVITY_MODULE_BUILDERS } from '@/views/home/activityModuleFactory'
import type { ActivityModuleContext, HomeActivityModule } from '@/views/home/activityModules/types'
import { buildBlueArchiveActivityPresentation } from '@/views/home/activityModules/bluearchive'
import { blueArchivePresentation } from '@/views/home/blueArchivePresentation'
import { useBlueArchiveActivitySource } from '@/views/home/useBlueArchiveActivitySource'
import type { HomeActivityEntry, HomeActivityPanel, ResourceItem } from '@/types/home'
import type { TaskboardActivity, TaskboardGameOption } from '@/types/taskboard'
import { useTaskboardStorage } from './useTaskboardStorage'

const ARCHIVE_KEEP_DAYS = 45
const DAY = 86400000
const URGENCY_DAYS = 30

const parseTs = (value?: string) => {
  if (!value) return 0
  // 已带时区的 ISO 直接解析，裸时间按北京时间补 +08:00
  const iso = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : value.replace(' ', 'T') + '+08:00'
  const ts = Date.parse(iso)
  return Number.isNaN(ts) ? 0 : ts
}

const nowText = () => {
  const date = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 首页活动卡的面板能直接转成任务台活动；可完成的额外分区（如常驻玩法）同样收录。 */
const panelActivities = (
  panel: Pick<HomeActivityPanel, 'activities' | 'extraSections'>
): HomeActivityEntry[] => [
  ...panel.activities.items,
  ...panel.extraSections.filter(section => section.completable).flatMap(section => section.items),
]

/**
 * 任务台的数据层：复用首页活动模块与完成状态接口，负责活动聚合、归档缓存和刷新。
 */
export const useTaskboardData = (t: Composer['t']) => {
  const resources = ref<ResourceItem[]>([])
  const resourceError = ref('')
  const moduleContext: ActivityModuleContext = { t, resources, resourceError }
  const gameModules = (
    Object.entries(HOME_ACTIVITY_MODULE_BUILDERS) as Array<
      [string, (context: ActivityModuleContext) => HomeActivityModule]
    >
  )
    .filter(([key]) => key !== 'bluearchive')
    .map(([key, build]) => [key, build(moduleContext)] as const)

  const baSource = useBlueArchiveActivitySource()

  const Game = GameCalendarActivityCompletionIn.game
  const Server = GameCalendarActivityCompletionIn.server
  const COMPLETION_SCOPES: Record<string, ActivityCompletionScope> = {
    endfield: { game: Game.ENDFIELD },
    starrail: { game: Game.STARRAIL },
    genshin: { game: Game.GENSHIN },
    zenless: { game: Game.ZENLESS },
    wutheringwaves: { game: Game.WUTHERINGWAVES },
    nte: { game: Game.NTE },
    infinitynikki: { game: Game.INFINITYNIKKI },
    arknights: { game: Game.ARKNIGHTS },
    stellasora: { game: Game.STELLASORA },
    reverse1999: { game: Game.REVERSE1999 },
    'bluearchive-cn': { game: Game.BLUEARCHIVE, server: Server.CN },
    'bluearchive-jp': { game: Game.BLUEARCHIVE, server: Server.JP },
    'bluearchive-global': { game: Game.BLUEARCHIVE, server: Server.GLOBAL },
  }
  const completions = new Map(
    Object.entries(COMPLETION_SCOPES).map(
      ([key, scope]) => [key, useActivityCompletionApi(scope)] as const
    )
  )

  const nowTs = ref(Date.now())
  const updatedAt = ref('')
  const refreshing = ref(false)
  const { cachedEvents, saveCache } = useTaskboardStorage()

  const gameMetas = computed<TaskboardGameOption[]>(() => {
    const out: TaskboardGameOption[] = []
    for (const [key, module] of gameModules) {
      const panel = module.buildPanel(nowTs.value)
      out.push({ key, name: panel.title, cover: panel.cover || '' })
    }
    for (const server of baSource.servers.value) {
      const overview = blueArchivePresentation(server.overview)
      out.push({
        key: `bluearchive-${server.key}`,
        name: `${t('home.game.bluearchive')} · ${server.label}`,
        cover: overview.cover || overview.activities.find(item => item.cover)?.cover || '',
      })
    }
    return out.sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  })

  const gameName = (key: string) => gameMetas.value.find(game => game.key === key)?.name || key

  /** 本次成功取到数据的游戏：数据源成功返回空列表时，旧活动仍应保留。 */
  const readyGameKeys = computed(() => {
    const keys = new Set<string>()
    for (const [key, module] of gameModules) {
      if (module.buildPanel(nowTs.value).activities.available) keys.add(key)
    }
    for (const server of baSource.servers.value) {
      if (server.overview.Available) keys.add(`bluearchive-${server.key}`)
    }
    return keys
  })

  const currentEvents = computed<TaskboardActivity[]>(() => {
    const out: TaskboardActivity[] = []
    const push = (gameKey: string, list: HomeActivityEntry[]) => {
      for (const item of list || []) {
        if (!item?.name || !item.startTime || !item.endTime) continue
        out.push({
          id: `${gameKey}|${item.name}|${item.startTime}`,
          gameKey,
          title: item.name,
          start_time: item.startTime,
          end_time: item.endTime,
          description: item.description || '',
          image_url: item.image || item.fallbackImage || '',
        })
      }
    }
    for (const [key, module] of gameModules) {
      push(key, panelActivities(module.buildPanel(nowTs.value)))
    }
    for (const server of baSource.servers.value) {
      const panel = buildBlueArchiveActivityPresentation({
        game: Game.BLUEARCHIVE,
        overview: blueArchivePresentation(server.overview),
        loading: baSource.loadingByServer[server.key],
        now: nowTs.value,
        t,
      })
      push(`bluearchive-${server.key}`, panelActivities(panel))
    }
    return out
  })

  /* 数据源只保留当期活动，已结束的会消失；本地累积一份缓存补出「已归档」 */
  watch(
    currentEvents,
    list => {
      const map = new Map(cachedEvents.value.map(e => [e.id, e]))
      for (const e of list) map.set(e.id, e)
      const cutoff = Date.now()
      const present = new Set(list.map(e => e.id))
      const readyGames = readyGameKeys.value
      cachedEvents.value = [...map.values()].filter(e => {
        const end = parseTs(e.end_time)
        if (!end) return true
        if (end <= cutoff) return end + ARCHIVE_KEEP_DAYS * DAY > cutoff
        // 还没结束、但对应游戏的数据源里已经没有它时不再显示；
        // 游戏本身没取到数据时保留缓存，避免源临时失败丢内容。
        return present.has(e.id) || !readyGames.has(e.gameKey)
      })
      saveCache()
    },
    { immediate: true }
  )

  const allEvents = computed<TaskboardActivity[]>(() => {
    const map = new Map(cachedEvents.value.map(e => [e.id, e]))
    for (const e of currentEvents.value) map.set(e.id, e)
    const now = nowTs.value
    return [...map.values()].filter(e => {
      const end = parseTs(e.end_time)
      return !end || end + ARCHIVE_KEEP_DAYS * DAY > now
    })
  })

  const activityOf = (e: TaskboardActivity) => ({
    name: e.title,
    startTime: e.start_time,
    endTime: e.end_time,
  })
  const completionOf = (e: TaskboardActivity) => completions.get(e.gameKey)
  const completionError = computed(() => {
    for (const completion of completions.values()) {
      const error = completion.errorMessage.value
      if (error) return error
    }
    return ''
  })
  const completionLoading = computed(() =>
    [...completions.values()].some(completion => completion.loading.value)
  )
  const isCompleted = (e: TaskboardActivity) => completionOf(e)?.isCompleted(activityOf(e)) ?? false
  const isSaving = (e: TaskboardActivity) => completionOf(e)?.isSaving(activityOf(e)) ?? false
  const isCompletionReady = (e: TaskboardActivity) => completionOf(e)?.ready.value ?? false
  const doneAtOf = (e: TaskboardActivity) => completionOf(e)?.doneAtOf(activityOf(e)) ?? ''

  type ActivityState = 'active' | 'done' | 'archived' | 'upcoming'

  const stateOf = (e: TaskboardActivity): ActivityState => {
    const end = parseTs(e.end_time)
    if (end && end <= nowTs.value) return 'archived'
    if (isCompleted(e)) return 'done'
    // 还没开始的活动不算「进行中」，否则会把后面几期一起列出来。
    const start = parseTs(e.start_time)
    if (start && start > nowTs.value) return 'upcoming'
    return 'active'
  }

  const toggleCompletion = async (e: TaskboardActivity, target: 'active' | 'done') => {
    const completion = completionOf(e)
    if (!completion || !completion.ready.value) return
    // 时钟每 5 分钟才走一格，点击前用当前时间再判一次，避免给刚结束的活动打完成。
    nowTs.value = Date.now()
    if (target === 'done' && stateOf(e) !== 'active') return
    if (target === 'active' && stateOf(e) !== 'done') return
    if (target === 'done') {
      if (!isCompleted(e)) await completion.toggle(activityOf(e))
    } else if (isCompleted(e)) {
      await completion.toggle(activityOf(e))
    }
  }

  const countByOption = (option: TaskboardGameOption) =>
    allEvents.value.filter(e => e.gameKey === option.key && stateOf(e) === 'active').length

  const remaining = (e: TaskboardActivity) => parseTs(e.end_time) - nowTs.value

  const progressOf = (e: TaskboardActivity): number | null => {
    if (!e.end_time) return null
    const left = remaining(e)
    if (left <= 0) return 100
    const days = left / DAY
    return Math.max(4, Math.min(100, ((URGENCY_DAYS - days) / URGENCY_DAYS) * 100))
  }

  const progressColor = (e: TaskboardActivity) =>
    remaining(e) <= 7 * DAY ? 'var(--ant-color-error)' : 'var(--ant-color-primary)'

  const countdownOf = (
    e: TaskboardActivity
  ): { tone: 'muted' | 'normal' | 'urgent'; text: string } => {
    if (stateOf(e) === 'archived') {
      const left = Math.ceil((parseTs(e.end_time) + ARCHIVE_KEEP_DAYS * DAY - nowTs.value) / DAY)
      return {
        tone: 'muted',
        text: left > 0 ? t('taskboard.deleteInDays', { p0: left }) : t('taskboard.deleteToday'),
      }
    }
    const left = remaining(e)
    if (!e.end_time) return { tone: 'normal', text: '' }
    if (left <= 0) return { tone: 'muted', text: t('taskboard.ended') }
    if (left < 3600000) return { tone: 'urgent', text: t('taskboard.endsSoon') }
    if (left < DAY)
      return { tone: 'urgent', text: t('taskboard.leftHours', { p0: Math.ceil(left / 3600000) }) }
    const days = Math.ceil(left / DAY)
    return { tone: days <= 7 ? 'urgent' : 'normal', text: t('taskboard.leftDays', { p0: days }) }
  }

  /* 一律按北京时间显示：1999 源给的是 UTC（带 Z），直接切字符串会差 8 小时 */
  const fmtDate = (value?: string) => {
    const ts = parseTs(value)
    if (!ts) return t('taskboard.undetermined')
    const date = new Date(ts + 8 * 3600 * 1000)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`
  }

  const sourceIssues = computed(() => {
    const issues: string[] = []
    for (const [key, module] of gameModules) {
      const section = module.buildPanel(nowTs.value).activities
      if (!section.loading && !section.available) {
        issues.push(`${gameName(key)}: ${t('taskboard.sourceUnavailable')}`)
      } else if (section.stale) {
        issues.push(`${gameName(key)}: ${t('taskboard.sourceStale')}`)
      }
      for (const alert of section.alerts ?? []) {
        issues.push(`${gameName(key)}: ${alert.message}`)
      }
    }
    for (const server of baSource.servers.value) {
      const key = `bluearchive-${server.key}`
      if (!baSource.loadingByServer[server.key] && !server.overview.Available) {
        issues.push(`${gameName(key)}: ${t('taskboard.sourceUnavailable')}`)
      } else if (server.overview.Stale) {
        issues.push(`${gameName(key)}: ${t('taskboard.sourceStale')}`)
      }
    }
    return [...new Set(issues)]
  })

  const loading = computed(() => {
    const flags = [
      ...gameModules.map(([, module]) => module.buildPanel(nowTs.value).activities.loading),
      ...Object.values(baSource.loadingByServer),
    ]
    return flags.some(Boolean)
  })

  const reloadCompletions = async () => {
    await Promise.all([...completions.values()].map(completion => completion.load(true)))
  }

  const load = async () => {
    refreshing.value = true
    try {
      await Promise.all([
        ...gameModules.map(([, module]) => module.source.refresh()),
        baSource.refresh(),
        ...[...completions.values()].map(completion => completion.load(true)),
      ])
      if (!completionError.value && !sourceIssues.value.length) updatedAt.value = nowText()
    } finally {
      refreshing.value = false
    }
  }

  const sources = computed(() => [...gameModules.map(([, module]) => module.source), baSource])

  let timer: ReturnType<typeof setInterval> | null = null
  onMounted(() => {
    sources.value.forEach(source => source.start())
    void Promise.all([...completions.values()].map(completion => completion.load())).then(() => {
      if (!completionError.value && !sourceIssues.value.length) updatedAt.value = nowText()
    })
    timer = setInterval(() => {
      nowTs.value = Date.now()
    }, 300000)
  })
  onUnmounted(() => {
    sources.value.forEach(source => source.stop())
    if (timer) clearInterval(timer)
    timer = null
  })

  return {
    allEvents,
    completionLoading,
    completionError,
    countByOption,
    countdownOf,
    doneAtOf,
    fmtDate,
    gameMetas,
    gameName,
    isCompletionReady,
    isCompleted,
    isSaving,
    load,
    loading,
    nowTs,
    progressColor,
    progressOf,
    refreshing,
    reloadCompletions,
    sourceIssues,
    stateOf,
    toggleCompletion,
    updatedAt,
  }
}
