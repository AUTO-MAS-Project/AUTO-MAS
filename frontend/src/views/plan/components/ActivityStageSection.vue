<template>
  <div class="activity-stage-section">
    <!-- 摘要条：状态机压缩版，收起不丢信息 -->
    <button class="section-head" type="button" @click="onToggle">
      <CaretRightOutlined class="chev" :class="{ open: !collapsed }" />
      <span class="section-title">{{ t('plan.activity.title') }}</span>
      <span v-if="period === 'ongoing'" class="live-dot">
        <span class="dot"></span>{{ t('plan.activity.ongoing') }}
      </span>
      <span v-if="summaryActivityName" class="activity-name">{{ summaryActivityName }}</span>
      <span class="summary-pill" :class="{ warn: warningCount > 0 }">{{ summaryText }}</span>
      <span class="meta">{{ metaText }}</span>
    </button>

    <div v-if="!collapsed" class="section-body">
      <div v-if="loading" class="section-loading">
        <a-spin />
      </div>
      <a-alert v-else-if="error" type="error" :message="error" show-icon>
        <template #action>
          <a-button size="small" danger @click="loadData">
            {{ t('plan.activity.retry') }}
          </a-button>
        </template>
      </a-alert>
      <template v-else>
        <p class="hint">{{ t('plan.activity.hint') }}</p>

        <a-alert v-if="period === 'preview' && previewMeta" type="info" class="gap-banner" show-icon>
          <template #message>
            {{
              t('plan.activity.previewBanner', {
                name: previewMeta.name,
                start: previewMeta.startText,
              })
            }}
          </template>
        </a-alert>
        <a-alert v-else-if="period === 'gap'" type="info" class="gap-banner" show-icon>
          <template #message>{{ t('plan.activity.gapBanner') }}</template>
        </a-alert>

        <table class="slots">
          <thead>
            <tr>
              <th class="col-slot">{{ t('plan.activity.colSlot') }}</th>
              <th class="col-stage">{{ t('plan.activity.colStage') }}</th>
              <th>{{ t('plan.activity.colUsers') }}</th>
              <th class="col-status">{{ t('plan.activity.colStatus') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in slotRows" :key="row.key" :class="{ gap: row.notStarted, missing: !rowStageExists(row) }">
              <td>
                <span class="slot-name">{{ row.label }}</span>
              </td>
              <td>
                <template v-if="row.stageCode">
                  <span class="stage-code">{{ row.stageCode }}</span>
                  <span class="stage-mat">{{ row.stageMat }}</span>
                  <span v-if="row.notStarted" class="tag-future">{{ t('plan.activity.notStarted') }}</span>
                </template>
                <span v-else class="stage-none">
                  {{ row.skeleton ? t('plan.activity.pendingEntry') : t('plan.activity.noStage') }}
                </span>
              </td>
              <td>
                <div class="chips">
                  <span
                    v-for="item in usersInSlot(row.key)"
                    :key="item.user.userId"
                    class="chip"
                    :class="{
                      off: item.status.reason === 'switch-off',
                      dim: ['no-quick-config', 'user-disabled', 'gap', 'skipped'].includes(
                        item.status.reason,
                      ),
                    }"
                    :title="chipTitle(item)"
                  >
                    <span class="ava">{{ item.user.userName.slice(0, 1) }}</span>
                    <span class="nm">{{ item.user.userName }}</span>
                    <span class="srv">{{ serverDisplayName(item.user.server) }}</span>
                    <button
                      class="x"
                      type="button"
                      :disabled="saving"
                      :title="t('plan.activity.remove')"
                      @click="onRemoveUser(item.user)"
                    >✕</button>
                  </span>

                  <a-popover
                    :open="openSlotKey === row.key"
                    trigger="click"
                    placement="bottomLeft"
                    @open-change="
                      (open: boolean) => {
                        if (open) openSlotKey = row.key
                        else if (openSlotKey === row.key) openSlotKey = ''
                      }
                    "
                  >
                    <template #content>
                      <div class="pk-head" v-if="candidatesFor(row.key).unassigned.length">
                        {{ t('plan.activity.candidateUnassigned') }}
                      </div>
                      <button
                        v-for="user in candidatesFor(row.key).unassigned"
                        :key="user.userId"
                        class="pk"
                        type="button"
                        :disabled="saving"
                        @click="onAssignUser(user, row)"
                      >
                        <span>{{ user.userName }} · {{ serverDisplayName(user.server) }}</span>
                        <span class="frm">{{ t('plan.activity.joinSlot') }}</span>
                      </button>
                      <div class="pk-head" v-if="candidatesFor(row.key).fromOtherSlots.length">
                        {{ t('plan.activity.candidateOtherSlots') }}
                      </div>
                      <button
                        v-for="cand in candidatesFor(row.key).fromOtherSlots"
                        :key="cand.user.userId"
                        class="pk"
                        type="button"
                        :disabled="saving"
                        @click="onAssignUser(cand.user, row)"
                      >
                        <span>{{ cand.user.userName }} · {{ serverDisplayName(cand.user.server) }}</span>
                        <span class="frm move">{{ t('plan.activity.currentSlot', { slot: cand.fromLabel }) }}</span>
                      </button>
                      <div class="pk-head" v-if="!candidatesFor(row.key).unassigned.length && !candidatesFor(row.key).fromOtherSlots.length">
                        {{ t('plan.activity.noCandidates') }}
                      </div>
                    </template>
                    <button class="add-btn" type="button" :disabled="saving">＋ {{ t('plan.activity.addUser') }}</button>
                  </a-popover>
                </div>
              </td>
              <td>
                <span class="st" :class="rowStatusClass(row)">
                  <span class="d"></span>{{ rowStatusText(row) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="ghostUsers.length" class="unassigned">
          {{ t('plan.activity.notFollowing') }}
          <span v-for="user in ghostUsers" :key="user.userId" class="ghost-chip">
            {{ user.userName }} · {{ user.planLabel }}
          </span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CaretRightOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import type { ActivityItem } from '@/types/home'
import {
  buildSlotRows,
  readActivityMeta,
  resolveUserInjectStatus,
  slotKeyOfIntent,
  type ActivityUserRow,
  type StageSlotRow,
  type UserInjectStatus,
} from './activityStageSlots'

const props = defineProps<{
  planId: string
  /** 计划表 id → 名称映射，用于未跟随用户的归属标注 */
  planNames?: Record<string, string>
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('活动关指派')
const { getScriptsWithUsers, error: scriptApiError } = useScriptApi()
const { updateUser } = useUserApi()

// 折叠状态只记会话内组件状态（方案 §4.1，不进 localStorage）
const collapsed = ref(true)
const userTouched = ref(false)
const loading = ref(false)
const error = ref('')
const saving = ref(false)

const users = ref<ActivityUserRow[]>([])
const activityByServer = ref<Record<string, ActivityItem[]>>({})
const previewByServer = ref<Record<string, ActivityItem[]>>({})
/** 当前展开「添加用户」弹层的槽位键（同时只开一个） */
const openSlotKey = ref('')

// ==================== 视图状态推导 ====================

const SERVER_NAMES: Record<string, string> = {
  Official: '官服',
  Bilibili: 'B服',
  YoStarEN: '国际服',
  YoStarJP: '日服',
  YoStarKR: '韩服',
  txwy: '繁中服',
}
const serverDisplayName = (server: string) => SERVER_NAMES[server] ?? server
/** B服关卡数据与官服同源（后端 Bilibili→Official 归一） */
const stageServerOf = (server: string) => (server === 'Bilibili' ? 'Official' : server)

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

const followingUsers = computed(() =>
  usersView.value.filter(user => user.followsPlan),
)

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

interface UserSlotItem {
  user: ActivityUserRow
  status: UserInjectStatus
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

/** 添加用户候选：未指派的跟随用户 + 其他槽位用户（一人一槽，移入自动移出原槽） */
const candidatesFor = (rowKey: string) => {
  const unassigned = followingUsers.value.filter(user => !user.intent)
  const fromOtherSlots = followingUsers.value
    .filter(user => {
      const key = slotKeyOfIntent(user.intent)
      return key !== '' && key !== rowKey
    })
    .map(user => ({
      user,
      fromLabel: slotLabelOfIntent(user.intent),
    }))
  return { unassigned, fromOtherSlots }
}

const slotLabelOfIntent = (intent: string) => {
  const key = slotKeyOfIntent(intent)
  if (key === 'jade') return t('plan.activity.slotJade')
  if (key.startsWith('last:')) return t('plan.activity.slotLast', { n: key.slice(5) })
  return key
}

// ==================== 状态列 ====================

const rowUserStatuses = (row: StageSlotRow): UserSlotItem[] => usersInSlot(row.key)

const rowStageExists = (row: StageSlotRow) =>
  row.key === 'mat' || row.stageCode !== null

/** 行内需要黄字提示的用户：预览行与骨架行的 gap 是「待开启」不算警告 */
const rowBlockingItems = (row: StageSlotRow): UserSlotItem[] => {
  const warnReasons = [
    'no-match',
    'switch-off',
    'no-quick-config',
    'user-disabled',
    'skipped',
  ]
  return rowUserStatuses(row).filter(
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

const rowStatusClass = (row: StageSlotRow) => {
  const items = rowUserStatuses(row)
  if (!items.length) return row.notStarted ? 'muted' : 'idle'
  if (rowBlockingItems(row).length) return 'warn'
  // 骨架行上其他服有进行中活动的用户仍会真实注入，标 ok 而非置灰
  if (items.some(item => item.status.willInject)) return 'ok'
  if (row.notStarted) return 'muted'
  return 'ok'
}

const rowStatusText = (row: StageSlotRow): string => {
  const items = rowUserStatuses(row)
  if (!items.length) return t('plan.activity.statusIdle')
  const warnings = rowBlockingItems(row)
    .map(blockingText)
    .filter(text => text !== '')
  if (warnings.length) return warnings.join('；')
  const injectCount = items.filter(item => item.status.willInject).length
  if (injectCount > 0) return t('plan.activity.statusInject', { n: injectCount })
  return t('plan.activity.statusAwaiting', { n: items.length })
}

const warningCount = computed(() => slotRows.value.filter(row => rowStatusClass(row) === 'warn').length)

const assignedCount = computed(
  () => followingUsers.value.filter(user => user.intent).length,
)

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

const chipTitle = (item: UserSlotItem): string => blockingText(item)

// ==================== 数据加载与写回 ====================

/** 跳过簿命中判定：按用户自己服务器的进行中活动名对条目（后端同规则） */
const resolveSkipState = (
  user: { Info: { Server: string }; Data?: { ActivitySkipBook?: string } },
  activityMap: Record<string, ActivityItem[]>,
): { skipActive: boolean; skipDays: number; skipDetail: string } => {
  let book: Record<string, { date?: string; days?: number; detail?: string }> = {}
  try {
    const parsed = JSON.parse(user.Data?.ActivitySkipBook || '{ }')
    if (parsed && typeof parsed === 'object') book = parsed
  } catch {
    book = {}
  }
  const today = new Date(Date.now() + 4 * 3600_000).toISOString().slice(0, 10)
  const serverStages = activityMap[stageServerOf(user.Info.Server)] ?? []
  let skipActive = false
  let skipDays = 0
  let skipDetail = ''
  for (const [name, entry] of Object.entries(book)) {
    if (!entry || typeof entry !== 'object') continue
    // 与后端闸门同锚：条目活动必须仍在该服进行中才视为命中
    //（连错条目在活动结束、下轮运行时由后端修剪）
    const ongoingHere =
      Boolean(name) && serverStages.some(stage => stage.Activity?.StageName === name)
    const active = Boolean(ongoingHere) && ((entry.days ?? 0) >= 2 || entry.date === today)
    if (active && (entry.days ?? 0) >= skipDays) {
      skipActive = true
      skipDays = entry.days ?? 0
      skipDetail = [entry.detail, entry.date].filter(Boolean).join(' · ')
    }
  }
  return { skipActive, skipDays, skipDetail }
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
      (overviewResponse.data as { StageByServer?: Record<string, { Activity?: ActivityItem[]; Preview?: ActivityItem[] }> })
        .StageByServer ?? {}
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

const onAssignUser = async (
  user: ActivityUserRow,
  row: StageSlotRow,
) => {
  if (await persistIntent(user, row.key)) {
    openSlotKey.value = ''
    message.success(t('plan.activity.assignDone', { name: user.userName }))
  }
}

const onRemoveUser = async (user: ActivityUserRow) => {
  if (await persistIntent(user, '')) {
    message.success(t('plan.activity.removeDone', { name: user.userName }))
  }
}

const onToggle = () => {
  userTouched.value = true
  collapsed.value = !collapsed.value
}

// 出现需关注事项时自动展开一次（会话内一次性，不覆盖用户手动收起）
watch(
  [loading, warningCount],
  ([isLoading, warnings]) => {
    if (!isLoading && warnings > 0 && !userTouched.value && collapsed.value) {
      collapsed.value = false
    }
  },
  { immediate: true },
)

onMounted(() => {
  // 收起状态下也加载一份用户数据，保证摘要条的指派数与注意数可见
  void loadData()
})
</script>

<style scoped>
.activity-stage-section {
  margin-bottom: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  padding: 8px 16px 4px;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  background: none;
  border: none;
  padding: 4px 0 8px;
  color: inherit;
  text-align: left;
  font: inherit;
  cursor: pointer;
  flex-wrap: wrap;
}

.section-head .chev {
  color: var(--ant-color-text-tertiary);
  transition: transform 0.2s;
}

.section-head .chev.open {
  transform: rotate(90deg);
}

.section-head:hover .section-title {
  color: var(--ant-color-primary);
}

.section-title {
  font-size: 15px;
  font-weight: 600;
}

.live-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ant-color-success);
  background: var(--ant-color-success-bg);
  border-radius: 4px;
  padding: 1px 8px;
}

.live-dot .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-success);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}

.activity-name {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.summary-pill {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-tertiary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  padding: 1px 10px;
  white-space: nowrap;
}

.summary-pill.warn {
  color: var(--ant-color-warning);
  border-color: var(--ant-color-warning-border);
}

.section-head .meta {
  font-size: 12px;
  color: var(--ant-color-text-quaternary);
}

.section-body {
  padding: 2px 0 12px;
}

.section-loading {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin: 0 0 12px;
}

.gap-banner {
  margin-bottom: 12px;
}

table.slots {
  width: 100%;
  border-collapse: collapse;
}

table.slots th {
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  color: var(--ant-color-text-tertiary);
  padding: 8px 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  white-space: nowrap;
}

table.slots td {
  padding: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  vertical-align: middle;
}

table.slots tr:last-child td {
  border-bottom: none;
}

table.slots tr:hover td {
  background: var(--ant-color-fill-quaternary);
}

table.slots tr.gap td {
  opacity: 0.65;
}

table.slots tr.missing td {
  opacity: 0.55;
}

.col-slot {
  width: 130px;
}

.col-stage {
  width: 230px;
}

.col-status {
  width: 240px;
}

.slot-name {
  font-weight: 600;
  white-space: nowrap;
}

.slot-sub {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  font-weight: 400;
}

.stage-code {
  font-weight: 600;
}

.stage-mat {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  margin-left: 8px;
}

.stage-none {
  color: var(--ant-color-text-tertiary);
}

.tag-future {
  display: inline-block;
  font-size: 11px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  border-radius: 3px;
  padding: 0 6px;
  margin-left: 6px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--ant-color-border);
  border-radius: 16px;
  padding: 3px 6px 3px 4px;
  font-size: 13px;
  background: var(--ant-color-bg-container);
}

.chip .ava {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
}

.chip .nm {
  white-space: nowrap;
}

.chip .srv {
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
}

.chip .x {
  border: none;
  background: none;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 50%;
  cursor: pointer;
}

.chip .x:hover:not(:disabled) {
  color: var(--ant-color-error);
  background: var(--ant-color-error-bg);
}

.chip.off {
  border-style: dashed;
  color: var(--ant-color-text-tertiary);
}

.chip.dim {
  opacity: 0.6;
}

.add-btn {
  border: 1px dashed var(--ant-color-border);
  background: none;
  color: var(--ant-color-text-tertiary);
  border-radius: 16px;
  padding: 3px 12px;
  font-size: 13px;
  cursor: pointer;
}

.add-btn:hover:not(:disabled) {
  color: var(--ant-color-primary);
  border-color: var(--ant-color-primary);
}

.pk-head {
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
  padding: 6px 10px 2px;
}

.pk {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  border: none;
  background: none;
  color: var(--ant-color-text);
  text-align: left;
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.pk:hover {
  background: var(--ant-color-fill-quaternary);
}

.pk .frm {
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
}

.pk .frm.move {
  color: var(--ant-color-warning);
}

.unassigned {
  margin-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
  padding-top: 10px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.ghost-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px dashed var(--ant-color-border);
  color: var(--ant-color-text-tertiary);
  border-radius: 16px;
  padding: 2px 10px;
  font-size: 12px;
}

.st {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  white-space: normal;
}

.st .d {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.st.ok {
  color: var(--ant-color-text-secondary);
}

.st.ok .d {
  background: var(--ant-color-success);
}

.st.warn {
  color: var(--ant-color-warning);
}

.st.warn .d {
  background: var(--ant-color-warning);
}

.st.muted {
  color: var(--ant-color-text-tertiary);
}

.st.muted .d {
  background: var(--ant-color-text-quaternary);
}

.st.idle {
  color: var(--ant-color-text-quaternary);
}

.st.idle .d {
  background: none;
  border: 1px solid var(--ant-color-border);
}
</style>
