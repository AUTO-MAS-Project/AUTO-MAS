<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { AppstoreOutlined, EditOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
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
import type { HomeActivityEntry, ResourceItem } from '@/types/home'
import type { TaskboardActivity, TaskboardGameOption, TaskboardSection } from '@/types/taskboard'
import { useTaskboardStorage } from './useTaskboardStorage'

defineOptions({ name: 'TaskboardPage' })

const { t } = useI18n()

const ARCHIVE_KEEP_DAYS = 45
const DAY = 86400000

/* 活动集合取自首页各活动模块的 buildPanel 结果：过滤、分类、条数与首页卡片一致。
 * 碧蓝档案首页卡片是「一个模块内切三服」，这里按服拆成三项，同样用首页的展示构建函数。 */
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

/* 完成状态走首页同一套后端接口（/api/info/activity/completions），
 * 两边共用一份记录：任务台勾完成，首页卡片同步打勾，反之亦然。 */
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

const tab = ref<'active' | 'done' | 'archived'>('active')
const keyword = ref('')
const gameFilter = ref<string | undefined>(undefined)
const expanded = ref<Record<string, boolean>>({})
const nowTs = ref(Date.now())
const updatedAt = ref('')
const refreshing = ref(false)
const editOpen = ref(false)
const draftGames = ref<string[]>([])
const pickerKeyword = ref('')

const parseTs = (s?: string) => {
  if (!s) return 0
  // 已带时区的 ISO 直接解析，裸时间按北京时间补 +08:00
  const iso = /[zZ]|[+-]\d{2}:\d{2}$/.test(s) ? s : s.replace(' ', 'T') + '+08:00'
  const ts = Date.parse(iso)
  return Number.isNaN(ts) ? 0 : ts
}

const nowText = () => {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const { enabledKeys, cachedEvents, saveEnabledKeys, saveCache } = useTaskboardStorage()

/* 游戏清单：标题与封面都取首页模块的面板数据，碧蓝档案按日/国际/国三服各算一个 */
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

const gameName = (key: string) => gameMetas.value.find(g => g.key === key)?.name || key

/* 本次成功取到数据的游戏：用它判断缓存里的活动是否还该保留。
 * 不能用“有没有活动”来判断——数据源成功返回空列表时，旧活动仍应保留。 */
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

/* 首页各活动卡片当前列出的活动（与卡片上的 items 完全一致） */
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
    push(key, module.buildPanel(nowTs.value).activities.items)
  }
  for (const server of baSource.servers.value) {
    const panel = buildBlueArchiveActivityPresentation({
      game: GameCalendarActivityCompletionIn.game.BLUEARCHIVE,
      overview: blueArchivePresentation(server.overview),
      loading: baSource.loadingByServer[server.key],
      now: nowTs.value,
      t,
    })
    push(`bluearchive-${server.key}`, panel.activities.items)
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
      // 还没结束、但对应游戏的数据源里已经没有它（比如首页卡片只取前 N 条把它挤掉了），
      // 就不该继续显示；游戏本身没取到数据时保留缓存，避免源临时失败丢内容。
      return present.has(e.id) || !readyGames.has(e.gameKey)
    })
    saveCache()
  },
  { immediate: true }
)

const allEvents = computed<TaskboardActivity[]>(() => {
  const map = new Map(cachedEvents.value.map(e => [e.id, e]))
  for (const e of currentEvents.value) map.set(e.id, e)
  // 归档满 45 天的活动直接下线（不依赖数据源是否还返回它）
  const now = nowTs.value
  return [...map.values()].filter(e => {
    const end = parseTs(e.end_time)
    return !end || end + ARCHIVE_KEEP_DAYS * DAY > now
  })
})

const enabledOptions = computed(() => {
  if (!enabledKeys.value) return gameMetas.value
  const set = new Set(enabledKeys.value)
  return gameMetas.value.filter(o => set.has(o.key))
})

const enabledKeySet = computed(() => new Set(enabledOptions.value.map(o => o.key)))

const filteredPickerGames = computed(() => {
  const kw = pickerKeyword.value.trim().toLowerCase()
  if (!kw) return gameMetas.value
  return gameMetas.value.filter(o => o.name.toLowerCase().includes(kw))
})

const toggleDraft = (key: string) => {
  if (draftGames.value.includes(key)) draftGames.value = draftGames.value.filter(k => k !== key)
  else draftGames.value = [...draftGames.value, key]
}

const openEdit = () => {
  draftGames.value = enabledOptions.value.map(o => o.key)
  pickerKeyword.value = ''
  editOpen.value = true
}

const saveGames = () => {
  enabledKeys.value = [...draftGames.value]
  saveEnabledKeys()
  if (gameFilter.value && !enabledOptions.value.some(o => o.key === gameFilter.value))
    gameFilter.value = undefined
  editOpen.value = false
}

const toggleGame = (key: string) => {
  gameFilter.value = gameFilter.value === key ? undefined : key
}

const countByOption = (o: TaskboardGameOption) =>
  allEvents.value.filter(e => e.gameKey === o.key && stateOf(e) === 'active').length

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
const isCompleted = (e: TaskboardActivity) => completionOf(e)?.isCompleted(activityOf(e)) ?? false
const isSaving = (e: TaskboardActivity) => completionOf(e)?.isSaving(activityOf(e)) ?? false
const isCompletionReady = (e: TaskboardActivity) => completionOf(e)?.ready.value ?? false
const doneAtOf = (e: TaskboardActivity) => completionOf(e)?.doneAtOf(activityOf(e)) ?? ''

type ActivityState = 'active' | 'done' | 'archived' | 'upcoming'

const stateOf = (e: TaskboardActivity): ActivityState => {
  // 已结束的一律进归档；已达成只保留还没结束的活动
  const end = parseTs(e.end_time)
  if (end && end <= nowTs.value) return 'archived'
  if (isCompleted(e)) return 'done'
  // 还没开始的活动不算「进行中」：官方活动源会把后面几期的活动一起放出来，
  // 全塞进进行中会比官网日程多出一大截（比如绝区零 9 条里有 6 条是未来的）。
  const start = parseTs(e.start_time)
  if (start && start > nowTs.value) return 'upcoming'
  return 'active'
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return allEvents.value.filter(e => {
    if (!enabledKeySet.value.has(e.gameKey)) return false
    if (stateOf(e) !== tab.value) return false
    if (gameFilter.value && e.gameKey !== gameFilter.value) return false
    if (!kw) return true
    return e.title.toLowerCase().includes(kw) || gameName(e.gameKey).toLowerCase().includes(kw)
  })
})

/* 进行中 / 已达成：扁平列表，严格按结束时间从近到远；已归档：按游戏分组。
 * 未开始的活动不进入列表；把它们排到末尾会让剩 200 多天的长期活动排在
 * 只剩几天的活动前面，顺序看起来是乱的。 */
const byEndAsc = (a: TaskboardActivity, b: TaskboardActivity) =>
  parseTs(a.end_time) - parseTs(b.end_time)

const groupOfArchived = (list: TaskboardActivity[]): TaskboardSection[] => {
  const byGame = new Map<string, TaskboardActivity[]>()
  list.forEach(e => {
    const arr = byGame.get(e.gameKey)
    if (arr) arr.push(e)
    else byGame.set(e.gameKey, [e])
  })
  const groups = [...byGame.entries()].map(([key, items]) => ({
    id: key,
    name: gameName(key),
    showHead: true,
    items: [...items].sort((a, b) => parseTs(b.end_time) - parseTs(a.end_time)),
  }))
  groups.sort((a, b) => parseTs(b.items[0]?.end_time) - parseTs(a.items[0]?.end_time))
  return groups
}

const sections = computed<TaskboardSection[]>(() => {
  if (tab.value === 'archived') return groupOfArchived(filtered.value)
  const items = [...filtered.value].sort(byEndAsc)
  return items.length ? [{ id: '', name: '', showHead: false, items }] : []
})

const visibleItems = (sec: TaskboardSection) => {
  if (!sec.showHead || expanded.value[sec.id]) return sec.items
  return sec.items.slice(0, 4)
}

const counts = computed(() => {
  const c = { active: 0, done: 0, archived: 0 }
  allEvents.value.forEach(e => {
    if (!enabledKeySet.value.has(e.gameKey)) return
    if (gameFilter.value && e.gameKey !== gameFilter.value) return
    const state = stateOf(e)
    if (state === 'upcoming') return
    c[state] += 1
  })
  return c
})

const remaining = (e: TaskboardActivity) => parseTs(e.end_time) - nowTs.value

/* 紧迫度条：一个月内按剩余天数线性映射，越接近结束越满。
 * 不用「已过时间 / 总时长」——那样长活动和短活动没法横向比较
 *（剩 7 天的长活动会比剩 11 天的短活动条还短，看着很怪）。 */
const URGENCY_DAYS = 30
const progressOf = (e: TaskboardActivity): number | null => {
  if (!e.end_time) return null
  const left = remaining(e)
  if (left <= 0) return 100
  const days = left / DAY
  return Math.max(4, Math.min(100, ((URGENCY_DAYS - days) / URGENCY_DAYS) * 100))
}

const progressColor = (e: TaskboardActivity) =>
  remaining(e) <= 7 * DAY ? 'var(--ant-color-error)' : 'var(--ant-color-primary)'

const countdownTag = (e: TaskboardActivity) => {
  if (stateOf(e) === 'archived') {
    const left = Math.ceil((parseTs(e.end_time) + ARCHIVE_KEEP_DAYS * DAY - nowTs.value) / DAY)
    return {
      color: 'default',
      text: left > 0 ? t('taskboard.deleteInDays', { p0: left }) : t('taskboard.deleteToday'),
    }
  }
  const left = remaining(e)
  if (!e.end_time) return { color: 'blue', text: '' }
  if (left <= 0) return { color: 'default', text: t('taskboard.ended') }
  if (left < 3600000) return { color: 'red', text: t('taskboard.endsSoon') }
  if (left < DAY)
    return { color: 'red', text: t('taskboard.leftHours', { p0: Math.ceil(left / 3600000) }) }
  const days = Math.ceil(left / DAY)
  return { color: days <= 7 ? 'red' : 'blue', text: t('taskboard.leftDays', { p0: days }) }
}

/* 一律按北京时间显示：1999 源给的是 UTC（带 Z），直接切字符串会差 8 小时 */
const fmtDate = (s?: string) => {
  const ts = parseTs(s)
  if (!ts) return t('taskboard.undetermined')
  const d = new Date(ts + 8 * 3600 * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
}

const setStatus = async (e: TaskboardActivity, s: 'active' | 'done') => {
  const completion = completionOf(e)
  if (!completion || !completion.ready.value) return
  // 时钟每 5 分钟才走一格，点击前用当前时间再判一次，避免给刚结束的活动打完成。
  nowTs.value = Date.now()
  if (s === 'done' && stateOf(e) !== 'active') return
  if (s === 'active' && stateOf(e) !== 'done') return
  try {
    if (s === 'done') {
      if (!isCompleted(e)) await completion.toggle(activityOf(e))
    } else if (isCompleted(e)) {
      await completion.toggle(activityOf(e))
    }
  } catch {
    message.error(t('taskboard.saveFailed'))
  }
}

const hideCover = (ev: Event) => {
  const img = ev.target as HTMLImageElement
  img.style.display = 'none'
}

const toggleExpand = (gid: string) => {
  expanded.value[gid] = !expanded.value[gid]
}

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
    if (!completionError.value) updatedAt.value = nowText()
  } finally {
    refreshing.value = false
  }
}

const sources = computed(() => [...gameModules.map(([, module]) => module.source), baSource])

let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  sources.value.forEach(source => source.start())
  void Promise.all([...completions.values()].map(completion => completion.load())).then(() => {
    if (!completionError.value) updatedAt.value = nowText()
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
</script>

<template>
  <div class="taskboard-container">
    <div class="tb-header">
      <h1 class="page-title">{{ t('taskboard.title') }}</h1>
      <span class="tb-updated">
        {{ updatedAt ? t('taskboard.dataUpdated', { p0: updatedAt }) : t('taskboard.loading') }}
      </span>
      <a-button :loading="refreshing || loading" @click="load">{{
        t('taskboard.refresh')
      }}</a-button>
    </div>

    <div class="tb-content">
      <div class="tb-toolbar">
        <a-input-search
          v-model:value="keyword"
          :placeholder="t('taskboard.searchPlaceholder')"
          allow-clear
          style="max-width: 300px"
        />
        <span class="tb-total">
          {{ t('taskboard.total', { p0: counts.active + counts.done + counts.archived }) }}
        </span>
        <a-tooltip :title="t('taskboard.editGamesTip')">
          <a-button class="tb-edit-btn" @click="openEdit">
            <template #icon><EditOutlined /></template>
            {{ t('taskboard.editGames') }}
          </a-button>
        </a-tooltip>
      </div>

      <div class="tb-chips">
        <template v-if="enabledOptions.length">
          <a-tooltip :title="t('taskboard.summaryHint')">
            <a-tag
              class="tb-chip"
              role="button"
              tabindex="0"
              :color="gameFilter === undefined ? 'blue' : undefined"
              @click="gameFilter = undefined"
              @keydown.enter.prevent="gameFilter = undefined"
              @keydown.space.prevent="gameFilter = undefined"
            >
              <AppstoreOutlined />
              {{ t('taskboard.summary') }}
            </a-tag>
          </a-tooltip>
          <a-tag
            v-for="o in enabledOptions"
            :key="o.key"
            class="tb-chip"
            role="button"
            tabindex="0"
            :color="gameFilter === o.key ? 'blue' : undefined"
            @click="toggleGame(o.key)"
            @keydown.enter.prevent="toggleGame(o.key)"
            @keydown.space.prevent="toggleGame(o.key)"
          >
            {{ o.name }}
          </a-tag>
        </template>
        <span v-else class="tb-no-game">{{ t('taskboard.noGames') }}</span>
      </div>

      <a-tabs v-model:active-key="tab" type="card" class="tb-tabs">
        <a-tab-pane key="active" :tab="`${t('taskboard.tabActive')} ${counts.active}`" />
        <a-tab-pane key="done" :tab="`${t('taskboard.tabDone')} ${counts.done}`" />
        <a-tab-pane key="archived" :tab="`${t('taskboard.tabArchived')} ${counts.archived}`" />
      </a-tabs>

      <a-alert
        v-if="completionError"
        type="warning"
        show-icon
        class="tb-alert"
        :message="t('taskboard.completionFailed')"
        :description="completionError"
      >
        <template #action>
          <a-button size="small" @click="reloadCompletions">{{ t('taskboard.retry') }}</a-button>
        </template>
      </a-alert>
      <div v-if="tab === 'archived'" class="tb-hint">{{ t('taskboard.archiveHint') }}</div>

      <a-spin :spinning="loading && !allEvents.length">
        <div v-for="sec in sections" :key="sec.id" class="tb-group">
          <div v-if="sec.showHead" class="tb-group-head">
            <span class="tb-game-name">{{ sec.name }}</span>
            <span class="tb-game-count">{{ sec.items.length }}</span>
          </div>
          <div class="tb-grid">
            <a-card
              v-for="e in visibleItems(sec)"
              :key="e.id"
              size="small"
              class="tb-card"
              :class="{ done: stateOf(e) === 'done', archived: sec.showHead }"
            >
              <template #cover>
                <div class="tb-cover-wrap">
                  <img
                    v-if="e.image_url"
                    :src="e.image_url"
                    :alt="e.title"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    class="tb-cover"
                    @error="hideCover"
                  />
                </div>
              </template>
              <div class="tb-card-body">
                <div v-if="!sec.showHead" class="tb-card-game">{{ gameName(e.gameKey) }}</div>
                <div class="tb-card-head">
                  <a-tooltip
                    v-if="e.description"
                    :title="e.description"
                    placement="topLeft"
                    :overlay-style="{ maxWidth: '420px' }"
                  >
                    <span class="tb-card-title">{{ e.title }}</span>
                  </a-tooltip>
                  <span v-else class="tb-card-title" :title="e.title">{{ e.title }}</span>
                  <a-tag v-if="countdownTag(e).text" :color="countdownTag(e).color" class="tb-tag">
                    {{ countdownTag(e).text }}
                  </a-tag>
                </div>
                <div class="tb-card-time">
                  <span>{{ t('taskboard.startsAt') }} {{ fmtDate(e.start_time) }}</span>
                  <span>{{ t('taskboard.endsAt') }} {{ fmtDate(e.end_time) }}</span>
                  <span v-if="stateOf(e) === 'done' && doneAtOf(e)" class="tb-card-done">
                    {{ t('taskboard.doneAt', { p0: doneAtOf(e) }) }}
                  </span>
                </div>
                <a-progress
                  v-if="stateOf(e) === 'active' && progressOf(e) !== null"
                  :percent="progressOf(e) || 0"
                  :show-info="false"
                  size="small"
                  :stroke-color="progressColor(e)"
                  class="tb-progress"
                />
                <div v-if="!sec.showHead" class="tb-card-actions">
                  <a-button
                    v-if="stateOf(e) === 'active'"
                    size="small"
                    type="primary"
                    ghost
                    :loading="isSaving(e)"
                    :disabled="!isCompletionReady(e)"
                    @click="setStatus(e, 'done')"
                  >
                    {{ t('taskboard.complete') }}
                  </a-button>
                  <a-button
                    v-else-if="stateOf(e) === 'done'"
                    size="small"
                    :loading="isSaving(e)"
                    @click="setStatus(e, 'active')"
                  >
                    {{ t('taskboard.undo') }}
                  </a-button>
                </div>
              </div>
            </a-card>
          </div>
          <a-button
            v-if="sec.showHead && sec.items.length > 4"
            type="link"
            size="small"
            @click="toggleExpand(sec.id)"
          >
            {{
              expanded[sec.id]
                ? t('taskboard.collapse')
                : t('taskboard.more', { p0: sec.items.length - 4 })
            }}
          </a-button>
        </div>
        <a-empty v-if="!sections.length && !loading" :description="t('taskboard.empty')" />
      </a-spin>
    </div>

    <a-modal
      v-model:open="editOpen"
      :title="t('taskboard.editGames')"
      :width="'min(1000px, 92vw)'"
      :ok-text="t('taskboard.save')"
      :cancel-text="t('taskboard.cancel')"
      @ok="saveGames"
    >
      <p class="tb-edit-hint">{{ t('taskboard.editGamesHint') }}</p>
      <div class="tb-edit-tools">
        <a-input-search
          v-model:value="pickerKeyword"
          :placeholder="t('taskboard.searchGames')"
          allow-clear
          style="flex: 1"
        />
        <a-button size="small" @click="draftGames = gameMetas.map(o => o.key)">{{
          t('taskboard.selectAll')
        }}</a-button>
        <a-button size="small" @click="draftGames = []">{{ t('taskboard.clear') }}</a-button>
        <span class="tb-edit-count-total">{{
          t('taskboard.selectedCount', { p0: draftGames.length })
        }}</span>
      </div>
      <div class="tb-pick-grid">
        <div
          v-for="o in filteredPickerGames"
          :key="o.key"
          class="tb-pick"
          :class="{ on: draftGames.includes(o.key) }"
          @click="toggleDraft(o.key)"
        >
          <a-checkbox
            :checked="draftGames.includes(o.key)"
            class="tb-pick-check"
            @click.stop="toggleDraft(o.key)"
          />
          <div class="tb-pick-thumb">
            <img
              v-if="o.cover"
              :src="o.cover"
              :alt="o.name"
              loading="lazy"
              referrerpolicy="no-referrer"
              @error="hideCover"
            />
          </div>
          <div class="tb-pick-name" :title="o.name">{{ o.name }}</div>
          <div class="tb-pick-cnt">{{ t('taskboard.activeCount', { p0: countByOption(o) }) }}</div>
        </div>
        <div v-if="!filteredPickerGames.length" class="tb-pick-empty">
          {{ t('taskboard.empty') }}
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.taskboard-container {
  width: 100%;
  max-width: 1600px;
  margin: 0 auto;
  padding: 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.tb-header {
  margin-bottom: 16px;
  padding: 0 4px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--app-page-title-color, var(--ant-color-text));
}

.tb-updated {
  margin-right: auto;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-content {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 16px;
  width: 100%;
  flex: 1;
}

.tb-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 4px 6px;
}

.tb-total {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 2px 4px 10px;
}

.tb-chip {
  margin: 0;
  cursor: pointer;
  user-select: none;
  font-size: 16px;
  line-height: 28px;
  padding: 5px 15px;
  border-radius: 8px;
}

.tb-chip:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.tb-chip :deep(.anticon) {
  margin-right: 5px;
  vertical-align: -1px;
}

.tb-no-game {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.tb-edit-btn {
  margin-left: auto;
}

.tb-tabs :deep(.ant-tabs-nav) {
  margin: 0 0 14px;
  padding: 0 4px;
}

.tb-tabs :deep(.ant-tabs-nav .ant-tabs-tab.ant-tabs-tab) {
  font-size: 16px;
  padding: 12px 26px;
}

.tb-tabs :deep(.ant-tabs-nav .ant-tabs-tab .ant-tabs-tab-btn) {
  font-size: 16px;
}

.tb-tabs :deep(.ant-tabs-content-holder) {
  display: none;
}

.tb-hint {
  margin: 0 4px 12px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.tb-group {
  margin-bottom: 24px;
}

.tb-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 4px 10px;
}

.tb-game-name {
  font-weight: 700;
  font-size: 16px;
  color: var(--ant-color-text);
}

.tb-game-count {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}

.tb-card {
  display: flex;
  flex-direction: column;
  border-color: var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.tb-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
}

.tb-card.done {
  border-color: var(--ant-color-success-border);
}

/* 归档卡片没有按钮和进度条，收紧封面与标题，避免卡片下半截大片留白 */
.tb-card.archived .tb-cover-wrap {
  height: 128px;
}

.tb-card.archived .tb-card-title {
  min-height: 0;
  -webkit-line-clamp: 1;
  line-clamp: 1;
}

.tb-cover-wrap {
  height: 170px;
  background: var(--ant-color-fill-secondary);
}

.tb-cover {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tb-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tb-card-game {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-card-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.tb-card-title {
  flex: 1;
  min-height: 2.8em;
  font-weight: 600;
  font-size: 16px;
  line-height: 1.45;
  color: var(--ant-color-text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tb-tag {
  margin: 0;
  flex-shrink: 0;
  font-size: 14px;
  line-height: 22px;
  padding: 2px 10px;
}

.tb-card-time {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-card-done {
  color: var(--ant-color-success);
}

.tb-progress {
  margin: 0;
  line-height: 1;
}

.tb-progress :deep(.ant-progress-outer) {
  margin: 0;
  padding: 0;
}

.tb-card-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  margin-top: auto;
}

.tb-edit-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-edit-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.tb-edit-count-total {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.tb-pick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px;
  max-height: 58vh;
  overflow: auto;
  padding: 2px;
}

.tb-pick {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 10px 8px 12px;
  border: 2px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.15s;
  min-width: 0;
}

.tb-pick:hover {
  background: var(--ant-color-fill-quaternary);
}

.tb-pick.on {
  background: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-border);
}

.tb-pick-check {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
}

.tb-pick-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  overflow: hidden;
  background: var(--ant-color-fill-secondary);
}

.tb-pick-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.tb-pick-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  font-size: 14px;
  color: var(--ant-color-text);
}

.tb-pick-cnt {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-pick-empty {
  grid-column: 1 / -1;
  padding: 24px;
  text-align: center;
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}
</style>
