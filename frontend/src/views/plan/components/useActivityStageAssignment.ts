// 计划表页「活动关批量指派表」的数据与视图推导：加载、槽位行、用户注入状态、写回。
// 纯逻辑在 ./activityStageSlots，跨页共享原语在 @/utils/activityStage 与 @/utils/activitySkipBook；
// 组件（ActivityStageSection / ActivitySlotTable）只负责渲染。

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { Service } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import type { ActivityItem } from '@/types/home'
import {
  readActivityMeta,
  slotKeyOfIntent,
  stageServerOf,
} from '@/utils/activityStage'
import { getServerDisplayName } from '@/utils/serverLabel'
import {
  activeSkipEntry,
  activityToday,
  parseActivitySkipBook,
  skipSummary,
  type ActivitySkipBook,
} from '@/utils/activitySkipBook'
import {
  buildSlotRows,
  resolveUserInjectStatus,
  type ActivityUserRow,
  type StageSlotRow,
  type UserInjectStatus,
} from './activityStageSlots'

/** 槽位行上的单个用户：渲染与操作只用到这些字段（原行挂在 user 上供写回） */
export interface SlotUserItem {
  userId: string
  userName: string
  serverName: string
  /** 芯片浮层提示（阻塞原因；可注入用户为空串） */
  title: string
  /** off=总开关未开（虚线），dim=其它不生效原因（置灰） */
  variant: 'normal' | 'off' | 'dim'
  user: ActivityUserRow
}

/** 候选用户（「添加用户」弹层）：未指派 / 从其他槽位移入 */
export interface SlotCandidate {
  userId: string
  userName: string
  serverName: string
  /** 移入前的槽位名（未指派用户为空串） */
  fromLabel: string
  user: ActivityUserRow
}

/** 槽位行渲染模型：文案与状态都在这里算好，表格组件保持无逻辑 */
export interface SlotViewRow {
  key: string
  label: string
  stageCode: string | null
  stageMat: string | null
  notStarted: boolean
  skeleton: boolean
  rowClass: string
  statusClass: 'ok' | 'warn' | 'muted' | 'idle'
  statusText: string
  users: SlotUserItem[]
  candidates: { unassigned: SlotCandidate[]; fromOtherSlots: SlotCandidate[] }
}

interface UserSlotItem {
  user: ActivityUserRow
  status: UserInjectStatus
}

const rowStageExists = (row: StageSlotRow) => row.stageCode !== null

/** 组件传入的响应式 props 对象（读值写在计算属性里，依赖照常追踪） */
export interface ActivityAssignmentProps {
  planId: string
  /** 计划表 id → 名称映射，用于未跟随用户的归属标注 */
  planNames?: Record<string, string>
}

export function useActivityStageAssignment(props: ActivityAssignmentProps) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('活动关指派')
  const { getScriptsWithUsers, error: scriptApiError } = useScriptApi()
  const { updateUser } = useUserApi()

  const loading = ref(false)
  const error = ref('')
  const saving = ref(false)

  const users = ref<ActivityUserRow[]>([])
  const activityByServer = ref<Record<string, ActivityItem[]>>({})
  const previewByServer = ref<Record<string, ActivityItem[]>>({})

  // ==================== 视图状态推导 ====================

  /** 未跟随用户的归属描述（其他计划表名 / 固定模式） */
  const planLabelFor = (user: ActivityUserRow): string => {
    if (user.stageMode === 'Fixed') return t('plan.activity.planFixed')
    return props.planNames?.[user.stageMode] ?? t('plan.activity.planUnknown')
  }

  /** followsPlan/planLabel 随当前计划表派生，原始行只存 stageMode */
  const usersView = computed<ActivityUserRow[]>(() =>
    users.value.map(user => ({
      ...user,
      followsPlan: user.stageMode === props.planId,
      planLabel: planLabelFor(user),
    })),
  )

  const followingUsers = computed(() => usersView.value.filter(user => user.followsPlan))

  /** 锚定服务器 = 跟随用户中最常见的服务器（并列取先出现者，仅影响关卡展示列） */
  const anchorServer = computed(() => {
    const counts = new Map<string, number>()
    for (const user of followingUsers.value) {
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

  const activityStages = computed(
    () => activityByServer.value[stageServerOf(anchorServer.value)] ?? [],
  )
  const previewStages = computed(
    () => previewByServer.value[stageServerOf(anchorServer.value)] ?? [],
  )
  const period = computed<'ongoing' | 'preview' | 'gap'>(() => {
    if (activityStages.value.length) return 'ongoing'
    if (previewStages.value.length) return 'preview'
    return 'gap'
  })
  const displayStages = computed(() =>
    period.value === 'ongoing' ? activityStages.value : previewStages.value,
  )
  const ongoingMeta = computed(() => readActivityMeta(activityStages.value))
  const previewMeta = computed(() => readActivityMeta(previewStages.value))

  const assignedIntents = computed(() =>
    followingUsers.value.map(user => user.intent).filter(intent => intent !== ''),
  )

  const slotRows = computed(() =>
    buildSlotRows(displayStages.value, assignedIntents.value, period.value === 'preview'),
  )

  /** 用户自己服务器的期间态：注入判定必须按各服真实数据，不能用锚定服 */
  const periodForUser = (server: string): 'ongoing' | 'preview' | 'gap' => {
    const key = stageServerOf(server)
    if ((activityByServer.value[key] ?? []).length) return 'ongoing'
    if ((previewByServer.value[key] ?? []).length) return 'preview'
    return 'gap'
  }

  const stagesForUser = (server: string) => {
    const key = stageServerOf(server)
    const currentPeriod = periodForUser(server)
    if (currentPeriod === 'ongoing') return activityByServer.value[key] ?? []
    if (currentPeriod === 'preview') return previewByServer.value[key] ?? []
    return []
  }

  const usersInSlot = (rowKey: string): UserSlotItem[] =>
    followingUsers.value
      .filter(user => slotKeyOfIntent(user.intent) === rowKey)
      .map(user => ({
        user,
        status: resolveUserInjectStatus(
          user,
          stagesForUser(user.server),
          periodForUser(user.server),
        ),
      }))

  const ghostUsers = computed(() => usersView.value.filter(user => !user.followsPlan))

  const slotLabelOfIntent = (intent: string) => {
    const key = slotKeyOfIntent(intent)
    if (key === 'jade') return t('plan.activity.slotJade')
    if (key.startsWith('last:')) return t('plan.activity.slotLast', { n: key.slice(5) })
    return key
  }

  // ==================== 状态列 ====================

  /** 行内需要黄字提示的用户：预览行与骨架行的 gap 是「待开启」不算警告 */
  const rowBlockingItems = (row: StageSlotRow, items: UserSlotItem[]): UserSlotItem[] => {
    const warnReasons = [
      'no-match',
      'switch-off',
      'no-quick-config',
      'user-disabled',
      'skipped',
    ]
    return items.filter(
      item =>
        warnReasons.includes(item.status.reason) ||
        (item.status.reason === 'gap' && !row.notStarted),
    )
  }

  const blockingText = (item: UserSlotItem): string => {
    switch (item.status.reason) {
      case 'switch-off':
        return t('plan.activity.statusSwitchOff', { name: item.user.userName })
      case 'no-quick-config':
        return t('plan.activity.statusNoQuickConfig', { name: item.user.userName })
      case 'no-match':
        return t('plan.activity.statusUserNoMatch', { name: item.user.userName })
      case 'user-disabled':
        return t('plan.activity.statusUserDisabled', { name: item.user.userName })
      case 'skipped':
        return (item.user.skipDays ?? 0) >= 2
          ? t('plan.activity.statusUserSkipped', {
              name: item.user.userName,
              n: item.user.skipDays,
            })
          : t('plan.activity.statusUserSkippedToday', { name: item.user.userName })
      case 'gap':
        return t('plan.activity.statusUserGap', { name: item.user.userName })
      default:
        return ''
    }
  }

  const rowStatusClass = (row: StageSlotRow, items: UserSlotItem[]) => {
    if (!items.length) return row.notStarted ? 'muted' : 'idle'
    if (rowBlockingItems(row, items).length) return 'warn'
    // 骨架行上其他服有进行中活动的用户仍会真实注入，标 ok 而非置灰
    if (items.some(item => item.status.willInject)) return 'ok'
    if (row.notStarted) return 'muted'
    return 'ok'
  }

  const rowStatusText = (row: StageSlotRow, items: UserSlotItem[]): string => {
    if (!items.length) return t('plan.activity.statusIdle')
    const warnings = rowBlockingItems(row, items)
      .map(blockingText)
      .filter(text => text !== '')
    if (warnings.length) return warnings.join('；')
    const injectCount = items.filter(item => item.status.willInject).length
    if (injectCount > 0) return t('plan.activity.statusInject', { n: injectCount })
    return t('plan.activity.statusAwaiting', { n: items.length })
  }

  // ==================== 渲染模型（表格组件直接用） ====================

  const toSlotUser = (item: UserSlotItem): SlotUserItem => ({
    userId: item.user.userId,
    userName: item.user.userName,
    serverName: getServerDisplayName(item.user.server),
    title: blockingText(item),
    variant:
      item.status.reason === 'switch-off'
        ? 'off'
        : ['no-quick-config', 'user-disabled', 'gap', 'skipped'].includes(item.status.reason)
          ? 'dim'
          : 'normal',
    user: item.user,
  })

  const toCandidate = (user: ActivityUserRow, fromLabel = ''): SlotCandidate => ({
    userId: user.userId,
    userName: user.userName,
    serverName: getServerDisplayName(user.server),
    fromLabel,
    user,
  })

  /** 添加用户候选：未指派的跟随用户 + 其他槽位用户（一人一槽，移入自动移出原槽） */
  const candidatesFor = (rowKey: string) => ({
    unassigned: followingUsers.value.filter(user => !user.intent).map(user => toCandidate(user)),
    fromOtherSlots: followingUsers.value
      .filter(user => {
        const key = slotKeyOfIntent(user.intent)
        return key !== '' && key !== rowKey
      })
      .map(user => toCandidate(user, slotLabelOfIntent(user.intent))),
  })

  const slotViewRows = computed<SlotViewRow[]>(() =>
    slotRows.value.map(row => {
      const items = usersInSlot(row.key)
      const classes: string[] = []
      if (row.notStarted) classes.push('slots-row-gap')
      if (!rowStageExists(row)) classes.push('slots-row-missing')
      return {
        key: row.key,
        label: slotLabelOfIntent(row.key),
        stageCode: row.stageCode,
        stageMat: row.stageMat,
        notStarted: row.notStarted,
        skeleton: row.skeleton,
        rowClass: classes.join(' '),
        statusClass: rowStatusClass(row, items),
        statusText: rowStatusText(row, items),
        users: items.map(toSlotUser),
        candidates: candidatesFor(row.key),
      }
    }),
  )

  const warningCount = computed(
    () => slotViewRows.value.filter(row => row.statusClass === 'warn').length,
  )

  const assignedCount = computed(() => followingUsers.value.filter(user => user.intent).length)

  const summaryActivityName = computed(() => {
    if (period.value === 'ongoing') return ongoingMeta.value?.name ?? ''
    if (period.value === 'preview') return previewMeta.value?.name ?? ''
    return ''
  })

  const summaryText = computed(() => {
    if (period.value === 'preview' && previewMeta.value) {
      return t('plan.activity.summaryPreview', {
        start: previewMeta.value.startText,
        n: assignedCount.value,
      })
    }
    if (warningCount.value > 0) {
      return t('plan.activity.summaryWarn', { n: assignedCount.value, w: warningCount.value })
    }
    return t('plan.activity.summary', { n: assignedCount.value })
  })

  const metaText = computed(() => {
    if (period.value === 'ongoing' && ongoingMeta.value) {
      return t('plan.activity.metaOngoing', {
        start: ongoingMeta.value.startText,
        expire: ongoingMeta.value.expireText,
      })
    }
    if (period.value === 'preview') {
      return t('plan.activity.metaPreview')
    }
    return t('plan.activity.metaGap')
  })

  // ==================== 数据加载与写回 ====================

  /**
   * 跳过簿命中判定。解析与闸门走共享模块（与脚本页徽标、后端同锚）；
   * 额外要求条目活动仍在**该用户自己服务器**进行中——连错条目在活动结束后
   * 由后端在下一轮运行时修剪，这里先自行排除，避免把上期活动的旧条目算进本期。
   */
  const resolveSkipState = (
    user: { Info: { Server: string }; Data?: { ActivitySkipBook?: string } },
    activityMap: Record<string, ActivityItem[]>,
  ): { skipActive: boolean; skipDays: number; skipSummary: string } => {
    const serverStages = activityMap[stageServerOf(user.Info.Server)] ?? []
    const ongoingHere: ActivitySkipBook = {}
    for (const [name, entry] of Object.entries(
      parseActivitySkipBook(user.Data?.ActivitySkipBook),
    )) {
      if (serverStages.some(stage => stage.Activity?.StageName === name)) {
        ongoingHere[name] = entry
      }
    }
    const hit = activeSkipEntry(ongoingHere, activityToday())
    if (!hit) return { skipActive: false, skipDays: 0, skipSummary: '' }
    return {
      skipActive: true,
      skipDays: hit.entry.days ?? 0,
      skipSummary: skipSummary(hit.entry),
    }
  }

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
            StageByServer?: Record<
              string,
              { Activity?: ActivityItem[]; Preview?: ActivityItem[] }
            >
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
      for (const script of scripts) {
        if (script.type !== 'MAA') continue
        for (const user of script.users ?? []) {
          rows.push({
            scriptId: script.uid,
            scriptName: script.name,
            userId: user.id,
            userName: user.Info.Name,
            server: user.Info.Server,
            status: user.Info.Status,
            stageMode: user.Info.StageMode,
            followsPlan: false,
            planLabel: '',
            ifQuickConfig: user.Info.IfQuickConfig ?? true,
            ifActivityFirst: user.Task?.IfActivityFirst ?? false,
            intent: user.Task?.ActivityStageIntent ?? '',
            ...resolveSkipState(user, activityMap),
          })
        }
      }
      users.value = rows
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

  const persistIntent = async (user: ActivityUserRow, intent: string) => {
    saving.value = true
    try {
      // updateUser 失败（含运行锁、非 200）自行弹错并返回 false，不会抛出
      const ok = await updateUser(user.scriptId, user.userId, {
        Task: { ActivityStageIntent: intent },
      })
      if (!ok) return false
      // 写回原始行（视图行是派生副本，改它会在下次重算时丢失）
      const raw = users.value.find(
        row => row.scriptId === user.scriptId && row.userId === user.userId,
      )
      if (raw) raw.intent = intent
      return true
    } catch (e) {
      logger.error(`写回活动关意图异常: ${e instanceof Error ? e.message : String(e)}`)
      return false
    } finally {
      saving.value = false
    }
  }

  const assignUser = async (user: ActivityUserRow, row: SlotViewRow) => {
    if (await persistIntent(user, row.key)) {
      message.success(t('plan.activity.assignDone', { name: user.userName }))
    }
  }

  const removeUser = async (user: ActivityUserRow) => {
    if (await persistIntent(user, '')) {
      message.success(t('plan.activity.removeDone', { name: user.userName }))
    }
  }

  onMounted(() => {
    // 收起状态下也加载一份用户数据，保证摘要条的指派数与注意数可见
    void loadData()
  })

  return {
    loading,
    error,
    saving,
    period,
    ghostUsers,
    slotViewRows,
    previewMeta,
    summaryActivityName,
    summaryText,
    metaText,
    warningCount,
    loadData,
    assignUser,
    removeUser,
  }
}
