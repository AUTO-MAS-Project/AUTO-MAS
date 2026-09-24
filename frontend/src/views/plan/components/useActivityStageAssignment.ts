// 计划表页「活动关指派表」的数据与视图推导：加载、用户行、选关选项、多选写回。
// 纯逻辑在 ./activityUserRows，跨页共享原语在 @/utils/activityStage 与
// @/utils/activitySkipBook；组件（ActivityStageSection / ActivityUserTable）只渲染。
//
// 配置层级是「用户级唯一来源」：每个用户自己持有总开关与选关意图，本表是批量
// 视图，改动立即写回该用户配置，没有计划级默认值、也没有继承关系。

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { Service } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import type { ActivityItem } from '@/types/home'
import {
  ongoingSkipBook,
  activeSkipEntry,
  parseActivitySkipBook,
  skipSummary,
} from '@/utils/activitySkipBook'
import { readActivityMeta, stageServerOf } from '@/utils/activityStage'
import {
  buildIntentOptions,
  matchesFilter,
  resolveUserState,
  summarizeRows,
  STATE_LABEL_KEYS,
  type ActivityFilter,
  type ActivityUserRow,
  type ActivityUserRowView,
  type ActivityUserState,
  type IntentOption,
  type IntentOptionView,
} from './activityUserRows'

/** 期间态：进行中 / 下期预览（仅预览不注入）/ 间隙期 */
type Period = 'ongoing' | 'preview' | 'gap'

export interface ActivityAssignmentProps {
  planId: string
}

export function useActivityStageAssignment(props: ActivityAssignmentProps) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('活动关指派')
  const { getScriptsWithUsers, error: scriptApiError } = useScriptApi()
  const { updateUser } = useUserApi()

  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const filter = ref<ActivityFilter>('all')

  /** 本表跟随用户（其余用户不在此列表，底部给一行提示） */
  const users = ref<ActivityUserRow[]>([])
  const otherUsersCount = ref(0)
  const activityByServer = ref<Record<string, ActivityItem[]>>({})
  const previewByServer = ref<Record<string, ActivityItem[]>>({})
  const selectedKeys = ref<Set<string>>(new Set())

  const rowKeyOf = (user: ActivityUserRow) => `${user.scriptId}:${user.userId}`

  /** 锚定服务器 = 跟随用户中最常见的服务器（并列取先出现者，仅影响表头信息） */
  const anchorServer = computed(() => {
    const counts = new Map<string, number>()
    for (const user of users.value) {
      counts.set(user.server, (counts.get(user.server) ?? 0) + 1)
    }
    let best = 'Official'
    let bestCount = -1
    for (const [server, count] of counts) {
      if (count > bestCount) {
        best = server
        bestCount = count
      }
    }
    return best
  })

  /** 注入判定必须按各服真实数据，不能用锚定服 */
  const periodForUser = (server: string): Period => {
    const key = stageServerOf(server)
    if ((activityByServer.value[key] ?? []).length) return 'ongoing'
    if ((previewByServer.value[key] ?? []).length) return 'preview'
    return 'gap'
  }

  const stagesForUser = (server: string): ActivityItem[] => {
    const key = stageServerOf(server)
    return periodForUser(server) === 'ongoing'
      ? (activityByServer.value[key] ?? [])
      : (previewByServer.value[key] ?? [])
  }

  const period = computed<Period>(() => periodForUser(anchorServer.value))
  const anchorStages = computed(() =>
    period.value === 'ongoing'
      ? (activityByServer.value[stageServerOf(anchorServer.value)] ?? [])
      : (previewByServer.value[stageServerOf(anchorServer.value)] ?? [])
  )
  const anchorMeta = computed(() => readActivityMeta(anchorStages.value))

  /**
   * 跳过簿命中判定。解析与闸门走共享模块（与后端同锚）；额外要求条目活动仍在
   * 该用户自己服务器上——旧条目在后端下一轮运行才修剪，这里先自行排除。
   */
  const resolveSkipState = (user: {
    Info: { Server: string }
    Data?: { ActivitySkipBook?: string }
  }): Pick<ActivityUserRow, 'skipToday' | 'skipDays' | 'skipSummary'> => {
    const serverKey = stageServerOf(user.Info.Server)
    const ongoingNames = new Set(
      (activityByServer.value[serverKey] ?? [])
        .map(stage => stage.Activity?.StageName)
        .filter((name): name is string => Boolean(name))
    )
    const hit = activeSkipEntry(
      ongoingSkipBook(parseActivitySkipBook(user.Data?.ActivitySkipBook), ongoingNames)
    )
    if (!hit) return { skipToday: false, skipDays: 0, skipSummary: '' }
    return {
      skipToday: true,
      skipDays: hit.entry.days ?? 0,
      skipSummary: skipSummary(hit.entry),
    }
  }

  const labelOfOption = (option: IntentOption) => t(option.labelKey, option.labelParams)

  const stateLabel = (state: ActivityUserState) => t(STATE_LABEL_KEYS[state])

  /** 行视图：状态与选项按该行自己服务器的期间态与关卡算 */
  const rowsView = computed<ActivityUserRowView[]>(() =>
    users.value.map(row => {
      const stages = stagesForUser(row.server)
      const rowPeriod = periodForUser(row.server)
      const state = resolveUserState(row, stages, rowPeriod)
      return {
        key: rowKeyOf(row),
        row,
        state,
        stateText: stateLabel(state),
        period: rowPeriod,
        options: buildIntentOptions(stages, row.intent).map(option => ({
          ...option,
          label: labelOfOption(option),
        })),
        skipDetail: row.skipToday
          ? [row.skipSummary, row.skipDays > 1 ? `连错 ${row.skipDays} 天` : '']
              .filter(Boolean)
              .join(' · ')
          : '',
      }
    })
  )

  const visibleRows = computed(() =>
    rowsView.value.filter(view => matchesFilter(view.state, filter.value))
  )

  const summary = computed(() => summarizeRows(rowsView.value.map(view => view.state)))

  /** 还没选关的跟随用户数（筛选条上的入口） */
  const noIntentCount = computed(
    () => rowsView.value.filter(view => view.state === 'no-intent').length
  )

  const selectedCount = computed(() => selectedKeys.value.size)
  const allSelected = computed(
    () =>
      visibleRows.value.length > 0 &&
      visibleRows.value.every(view => selectedKeys.value.has(view.key))
  )
  const someSelected = computed(
    () => !allSelected.value && visibleRows.value.some(view => selectedKeys.value.has(view.key))
  )

  /** 批量选关的选项锚定在锚定服（意图本身跨服通用，各号按自己服务器解析） */
  const bulkStageOptions = computed<IntentOptionView[]>(() =>
    buildIntentOptions(anchorStages.value, '').map(option => ({
      ...option,
      label: labelOfOption(option),
    }))
  )

  const metaText = computed(() => {
    if (period.value === 'ongoing' && anchorMeta.value) {
      return t('plan.activity.metaOngoing', {
        start: anchorMeta.value.startText,
        expire: anchorMeta.value.expireText,
      })
    }
    if (period.value === 'preview') return t('plan.activity.metaPreview')
    return t('plan.activity.metaGap')
  })

  const summaryText = computed(() => {
    if (summary.value.attention > 0) {
      return t('plan.activity.summaryWarn', {
        n: summary.value.followed,
        w: summary.value.attention,
      })
    }
    return t('plan.activity.summary', { n: summary.value.followed })
  })

  // ==================== 加载与写回 ====================

  const loadData = async () => {
    loading.value = true
    error.value = ''
    try {
      const [scripts, overviewResponse] = await Promise.all([
        getScriptsWithUsers(),
        Service.getOverviewApiInfoGetOverviewPost(),
      ])
      // getScriptsWithUsers 会吞掉单脚本失败并返回部分数据（error 置位）：
      // 降级展示部分数据 + 一次性提示，而不是整页报错
      let partialWarning = false
      if (scriptApiError.value) {
        partialWarning = true
        logger.warn(`部分脚本的用户数据获取失败: ${scriptApiError.value}`)
      }
      if (overviewResponse.code !== 200 || !overviewResponse.data) {
        throw new Error(overviewResponse.message || t('plan.activity.loadFailed'))
      }
      const stageByServer =
        (
          overviewResponse.data as {
            StageByServer?: Record<string, { Activity?: ActivityItem[]; Preview?: ActivityItem[] }>
          }
        ).StageByServer ?? {}
      const activityMap: Record<string, ActivityItem[]> = {}
      const previewMap: Record<string, ActivityItem[]> = {}
      for (const [server, overview] of Object.entries(stageByServer)) {
        activityMap[server] = overview.Activity ?? []
        previewMap[server] = overview.Preview ?? []
      }
      activityByServer.value = activityMap
      previewByServer.value = previewMap

      const rows: ActivityUserRow[] = []
      let others = 0
      for (const script of scripts) {
        if (script.type !== 'MAA') continue
        for (const user of script.users ?? []) {
          // 本表只管跟随这张计划表的用户：意图是用户级字段，其他表的用户在各自
          // 表的页面或用户编辑页调整（底部给一行提示，不在此列表里混排）
          if (user.Info.StageMode !== props.planId) {
            others += 1
            continue
          }
          rows.push({
            scriptId: script.uid,
            scriptName: script.name,
            userId: user.id,
            userName: user.Info.Name,
            server: user.Info.Server,
            status: user.Info.Status,
            stageMode: user.Info.StageMode,
            ifQuickConfig: user.Info.IfQuickConfig ?? true,
            ifActivityFirst: user.Task?.IfActivityFirst ?? false,
            intent: user.Task?.ActivityStageIntent ?? '',
            ...resolveSkipState(user),
          })
        }
      }
      users.value = rows
      otherUsersCount.value = others
      selectedKeys.value = new Set()
      if (partialWarning) {
        message.warning(t('plan.activity.partialLoad'))
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`加载活动关指派数据失败: ${errorMsg}`)
      error.value = t('plan.activity.loadFailed')
    } finally {
      loading.value = false
    }
  }

  /** 单字段写回：updateUser 失败（含运行锁、非 200）自行弹错并返回 false */
  const persist = async (
    row: ActivityUserRow,
    patch: Record<string, unknown>
  ): Promise<boolean> => {
    try {
      return await updateUser(row.scriptId, row.userId, { Task: patch })
    } catch (e) {
      logger.error(`写回活动关配置异常: ${e instanceof Error ? e.message : String(e)}`)
      return false
    }
  }

  /** 行内改动：写回后同步本地原始行（视图行是派生副本，改它会下次重算时丢失） */
  const persistRow = async (view: ActivityUserRowView, patch: Record<string, unknown>) => {
    saving.value = true
    try {
      if (!(await persist(view.row, patch))) return
      const raw = users.value.find(row => rowKeyOf(row) === view.key)
      if (!raw) return
      if ('ActivityStageIntent' in patch) {
        raw.intent = String(patch.ActivityStageIntent ?? '')
      }
      if ('IfActivityFirst' in patch) {
        raw.ifActivityFirst = patch.IfActivityFirst === true
      }
    } finally {
      saving.value = false
    }
  }

  const setRowIntent = (view: ActivityUserRowView, intent: string) =>
    persistRow(view, { ActivityStageIntent: intent })

  const setRowSwitch = (view: ActivityUserRowView, checked: boolean) =>
    persistRow(view, { IfActivityFirst: checked })

  /**
   * 批量应用：只写动过的字段（两个控件默认「不修改」）；逐人一次单字段 PATCH，
   * 失败的留在选中态并逐个报名字，成功的取消选中。
   */
  const applyBulk = async (toggle?: boolean | null, intent?: string | null) => {
    const targetKeys = [...selectedKeys.value]
    const targets = rowsView.value.filter(view => targetKeys.includes(view.key))
    if (!targets.length) return
    const patch: Record<string, unknown> = {}
    if (toggle === true || toggle === false) patch.IfActivityFirst = toggle
    if (typeof intent === 'string') patch.ActivityStageIntent = intent
    if (!Object.keys(patch).length) return

    saving.value = true
    const failed: string[] = []
    try {
      for (const view of targets) {
        if (!(await persist(view.row, { ...patch }))) {
          failed.push(view.row.userName)
          continue
        }
        const raw = users.value.find(row => rowKeyOf(row) === view.key)
        if (raw) {
          if ('ActivityStageIntent' in patch) {
            raw.intent = String(patch.ActivityStageIntent ?? '')
          }
          if ('IfActivityFirst' in patch) raw.ifActivityFirst = patch.IfActivityFirst === true
        }
        selectedKeys.value.delete(view.key)
      }
    } finally {
      saving.value = false
    }
    if (failed.length) {
      message.error(t('plan.activity.bulkPartial', { n: failed.length, names: failed.join('、') }))
      return
    }
    message.success(t('plan.activity.bulkApplied', { n: targets.length }))
  }

  const toggleSelect = (key: string, checked: boolean) => {
    if (checked) selectedKeys.value.add(key)
    else selectedKeys.value.delete(key)
  }

  const toggleSelectAll = (checked: boolean) => {
    for (const view of visibleRows.value) toggleSelect(view.key, checked)
  }

  onMounted(() => {
    // 收起状态下也加载一份数据，保证摘要条的人数与注意数可见
    void loadData()
  })

  return {
    loading,
    saving,
    error,
    filter,
    period,
    metaText,
    summaryText,
    visibleRows,
    noIntentCount,
    summary,
    activityName: computed(() => anchorMeta.value?.name ?? ''),
    otherUsersCount,
    bulkStageOptions,
    selectedKeys,
    selectedCount,
    allSelected,
    someSelected,
    loadData,
    setRowIntent,
    setRowSwitch,
    applyBulk,
    toggleSelect,
    toggleSelectAll,
  }
}
