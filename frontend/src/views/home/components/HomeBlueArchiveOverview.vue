<template>
  <a-card
    :title="t('home.module.bluearchive')"
    class="bluearchive-card"
    :style="cardStyle"
    :loading="currentLoading"
  >
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          href="https://kivo.wiki/timeline"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          {{ t('home.bluearchive.source') }}
        </a-typography-link>
        <a-tag v-if="overview.Stale" color="orange">{{ t('home.bluearchive.stale') }}</a-tag>
      </div>
    </template>

    <!-- 三个服的数据在数据源里已并行拉好，这里只切显示，不重新请求 -->
    <div class="server-switch" role="group" :aria-label="t('home.bluearchive.serverLabel')">
      <span class="server-switch-label">{{ t('home.bluearchive.serverLabel') }}</span>
      <!-- 拖动即可调整顺序，顺序记在本地 -->
      <div class="server-tabs" :title="t('home.bluearchive.serverDragHint')">
        <button
          v-for="(server, index) in orderedServers"
          :key="server.key"
          type="button"
          class="server-tab"
          :class="{ 'is-active': server.key === selected, 'is-dragging': dragIndex === index }"
          @click="emit('select', server.key)"
          @dragover.prevent="onDragOver(index)"
          @dragend="onDragEnd"
          @drop.prevent="onDragEnd"
        >
          <DragOutlined
            class="server-drag-handle"
            draggable="true"
            :aria-label="t('home.bluearchive.serverDragHint')"
            @click.stop
            @dragstart.stop="onDragStart(index, $event)"
            @dragend.stop="onDragEnd"
          />
          {{ server.label }}
        </button>
      </div>
    </div>

    <!-- 当前服的失败提示：只影响这一个服，切到其它服照常显示 -->
    <a-alert
      v-if="overview.Message"
      :message="overview.Message"
      :type="overview.Available ? 'warning' : 'error'"
      show-icon
      class="status-alert"
    />

    <div
      v-if="overview.Available && !currentLoading && !overview.activities.length"
      class="empty-state"
    >
      <a-empty :description="t('home.bluearchive.noActivity')" />
    </div>

    <!-- 活动 Banner（超高竖图只显示上部条带） -->
    <div v-else-if="overview.Available && !currentLoading && versionCover" class="version-banner">
      <img
        :src="versionCover"
        :alt="overview.versionName"
        class="version-cover"
        @error="failedVersionCover = true"
      />
      <div class="version-overlay" />

      <div class="version-content">
        <div class="version-badge">
          <span class="badge-dot" />
          <span class="badge-text">{{
            t('home.bluearchive.versionBadge', { version: overview.version })
          }}</span>
        </div>

        <div class="version-name">{{ overview.versionName }}</div>

        <div class="version-time">
          <ClockCircleOutlined class="version-time-icon" />
          <span>{{ t('home.bluearchive.endsAt', { time: formatTime(overview.endTime) }) }}</span>
        </div>

        <div v-if="activeActivities.length" class="activity-tags">
          <a-tag
            v-for="activity in activeActivities"
            :key="`${activity.name}-${activity.endTime}`"
            class="activity-tag"
          >
            {{ activity.name }}
          </a-tag>
        </div>
      </div>

      <div class="version-remaining">
        <div class="remaining-label">{{ t('home.bluearchive.versionRemaining') }}</div>
        <a-statistic-countdown
          :value="getCountdownValue(overview.endTime)"
          :format="t('home.countdown.dh')"
          :value-style="remainingCountdownStyle"
        />
        <div class="remaining-sub">{{ t('home.bluearchive.nextVersionSoon') }}</div>
      </div>
    </div>

    <!-- 无活动封面：简洁信息条 -->
    <div v-else-if="overview.Available && !currentLoading" class="version-info">
      <div class="version-info-left">
        <div class="version-info-name">{{ overview.versionName }}</div>
        <div class="version-info-time">
          <ClockCircleOutlined class="version-info-time-icon" />
          <span class="version-info-time-label">{{ t('home.bluearchive.versionTime') }}</span>
          <span class="version-info-time-value"
            >{{ formatTime(overview.startTime) }} ~ {{ formatTime(overview.endTime) }}</span
          >
        </div>
      </div>

      <div class="version-info-right">
        <a-statistic-countdown
          :title="t('home.bluearchive.versionRemaining')"
          :value="getCountdownValue(overview.endTime)"
          :format="
            getPlainTimeStatus(overview.endTime) === 'ended'
              ? t('home.countdown.ended')
              : t('home.countdown.dh')
          "
          :value-style="plainRemainingCountdownStyle"
        />
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { ClockCircleOutlined, DragOutlined } from '@ant-design/icons-vue'
import { createEmptySraActivityOverview } from '@/types/home'
import type {
  BlueArchiveActivityOverview,
  BlueArchiveServerKey,
  BlueArchiveServerOverview,
} from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'

defineOptions({ name: 'HomeBlueArchiveOverview' })

const { t } = useI18n()

const props = defineProps<{
  servers: BlueArchiveServerOverview[]
  selected: BlueArchiveServerKey
  loadingByServer: Record<BlueArchiveServerKey, boolean>
}>()

const emit = defineEmits<{
  select: [server: BlueArchiveServerKey]
}>()

const ACCENT = '#3ba9ee'
const MAX_VISIBLE_ACTIVITIES = 4
const failedVersionCover = ref(false)

const cardStyle = computed<CSSProperties>(
  () =>
    ({
      '--bluearchive-accent': ACCENT,
    }) as CSSProperties
)

const currentServer = computed(() => props.servers.find(server => server.key === props.selected))

const overview = computed<BlueArchiveActivityOverview>(
  () => currentServer.value?.overview ?? createEmptySraActivityOverview()
)

// 每个服各有自己的加载态，卡片只关心当前选中的这个服
const currentLoading = computed(() => props.loadingByServer[props.selected] === true)

// 封面加载失败是「上一张图」的结果，切换服务器时必须重新判定，否则一个服取不到图会拖累其它服
watch(
  () => props.selected,
  () => {
    failedVersionCover.value = false
  }
)

/** 服务器显示顺序的本地记忆键；顺序只影响展示，不影响各自取数 */
const SERVER_ORDER_STORAGE_KEY = 'auto-mas.home.bluearchive-server-order'

const readStoredOrder = (): BlueArchiveServerKey[] => {
  try {
    const raw = localStorage.getItem(SERVER_ORDER_STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    if (Array.isArray(parsed)) {
      return parsed.filter((key): key is BlueArchiveServerKey => typeof key === 'string')
    }
  } catch {
    // 记忆损坏时退回默认顺序即可，不影响卡片显示
  }
  return []
}

const serverOrder = ref<BlueArchiveServerKey[]>(readStoredOrder())
const dragIndex = ref<number | null>(null)

/** 按用户拖出来的顺序排列；顺序里还没有的（例如以后新增服务器）接在末尾 */
const orderedServers = computed(() => {
  const byKey = new Map(props.servers.map(server => [server.key, server]))
  const ordered = serverOrder.value
    .map(key => byKey.get(key))
    .filter((server): server is BlueArchiveServerOverview => server !== undefined)
  const listed = new Set(ordered.map(server => server.key))
  return [...ordered, ...props.servers.filter(server => !listed.has(server.key))]
})

const persistServerOrder = () => {
  try {
    localStorage.setItem(SERVER_ORDER_STORAGE_KEY, JSON.stringify(serverOrder.value))
  } catch {
    // 存储不可用时只保留本次会话的顺序
  }
}

const onDragStart = (index: number, event: DragEvent) => {
  dragIndex.value = index
  event.dataTransfer?.setData('text/plain', String(index))
}

/** 拖到哪一格就实时插到哪一格，松手才算数（dragend 统一落盘） */
const onDragOver = (index: number) => {
  const from = dragIndex.value
  if (from === null || from === index) return

  const keys = orderedServers.value.map(server => server.key)
  const [moved] = keys.splice(from, 1)
  keys.splice(index, 0, moved)
  serverOrder.value = keys
  dragIndex.value = index
}

const onDragEnd = () => {
  if (dragIndex.value === null) return
  dragIndex.value = null
  serverOrder.value = orderedServers.value.map(server => server.key)
  persistServerOrder()
}

const activeActivities = computed(() => {
  const now = Date.now()
  return overview.value.activities
    .filter(activity => {
      return (
        getCountdownValue(activity.startTime) <= now && getCountdownValue(activity.endTime) > now
      )
    })
    .sort((left, right) => getCountdownValue(left.endTime) - getCountdownValue(right.endTime))
    .slice(0, MAX_VISIBLE_ACTIVITIES)
})

const versionCover = computed(() => {
  if (failedVersionCover.value) return ''
  return (
    overview.value.cover ||
    overview.value.activities.find(activity => activity.cover)?.cover ||
    ''
  )
})

const remainingCountdownStyle = computed<CSSProperties>(() => ({
  color: ACCENT,
  fontSize: '28px',
  fontWeight: 700,
  lineHeight: 1.1,
  fontVariantNumeric: 'tabular-nums',
}))

const getPlainTimeStatus = (value: string): 'normal' | 'warning' | 'ended' => {
  const remaining = getCountdownValue(value) - Date.now()
  if (remaining <= 0) return 'ended'
  if (remaining <= 2 * 24 * 60 * 60 * 1000) return 'warning'
  return 'normal'
}

const plainRemainingCountdownStyle = computed<CSSProperties>(() => {
  const status = getPlainTimeStatus(overview.value.endTime)
  if (status === 'ended') {
    return { color: 'var(--ant-color-error)', fontWeight: 600, fontSize: '18px' }
  }
  if (status === 'warning') {
    return { color: 'var(--ant-color-warning)', fontWeight: 600, fontSize: '18px' }
  }
  return { color: 'var(--ant-color-text)', fontWeight: 600, fontSize: '18px' }
})

const getCountdownValue = (value: string) => new Date(value).getTime()

const formatTime = (value: string) =>
  new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
</script>

<style scoped>
.bluearchive-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.bluearchive-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.card-extra {
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-link {
  font-size: 13px;
}

.server-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.server-switch-label {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* 自己做分段控件而不用 a-segmented：那一排要能拖动排序 */
.server-tabs {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: 8px;
  background: var(--ant-color-fill-tertiary);
}

.server-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text);
  font-size: 14px;
  line-height: 22px;
  cursor: pointer;
  user-select: none;
  transition:
    background 0.2s,
    color 0.2s;
}

.server-drag-handle {
  color: var(--ant-color-text-tertiary);
  cursor: grab;
}

.server-drag-handle:active {
  cursor: grabbing;
}

.server-tab:hover {
  color: var(--bluearchive-accent);
}

.server-tab.is-active {
  background: var(--ant-color-bg-container);
  color: var(--bluearchive-accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.server-tab.is-dragging {
  opacity: 0.5;
}

.status-alert {
  margin-bottom: 16px;
}

.empty-state {
  padding: 24px 0;
}

/* ---------- 活动 Banner ---------- */
.version-banner {
  position: relative;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  min-height: 380px;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 10px;
  background:
    radial-gradient(
      ellipse at 78% 20%,
      color-mix(in srgb, var(--bluearchive-accent) 14%, transparent),
      transparent 55%
    ),
    radial-gradient(ellipse at 90% 85%, rgba(64, 128, 255, 0.18), transparent 60%),
    linear-gradient(135deg, #0b1220 0%, #101a2e 55%, #0e1a2b 100%);
}

.version-cover {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
  object-fit: cover;
  /* Kivo 时间轴配图多为竖图，只显示上部约 14% 处的条带 */
  object-position: right 14%;
}

.version-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    rgba(11, 18, 32, 0.9) 0%,
    rgba(11, 18, 32, 0.72) 42%,
    rgba(11, 18, 32, 0.15) 100%
  );
}

.version-content {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 28px 32px;
  color: white;
}

.version-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  padding: 4px 12px;
  margin-bottom: 12px;
  border: 1px solid color-mix(in srgb, var(--bluearchive-accent) 45%, transparent);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bluearchive-accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--bluearchive-accent) 80%, transparent);
}

.badge-text {
  color: var(--bluearchive-accent);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.version-name {
  margin-bottom: 14px;
  color: white;
  font-size: 30px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0.01em;
  overflow-wrap: anywhere;
}

.version-time {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  padding: 6px 16px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.5);
  color: white;
  font-size: 15px;
  font-weight: 500;
}

.version-time-icon {
  color: var(--bluearchive-accent);
  font-size: 15px;
}

/* ---------- 活动标签 ---------- */
.activity-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.activity-tag {
  margin-inline-end: 0;
  border: 1px solid color-mix(in srgb, var(--bluearchive-accent) 45%, transparent);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
  color: white;
  font-size: 13px;
  font-weight: 500;
  line-height: 22px;
}

/* ---------- 剩余时间 ---------- */
/* 贴右下角、压成一行：封面里的人物多在画面中部，浮层居中会挡脸 */
.version-remaining {
  position: relative;
  z-index: 1;
  align-self: flex-end;
  margin: 0 28px 20px 0;
  padding: 12px 22px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  border: 1px solid color-mix(in srgb, var(--bluearchive-accent) 35%, transparent);
  border-radius: 12px;
  background: rgba(11, 18, 32, 0.6);
  backdrop-filter: blur(10px);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.35),
    inset 0 0 24px color-mix(in srgb, var(--bluearchive-accent) 5%, transparent);
  white-space: nowrap;
}

.remaining-label {
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  line-height: 1;
  letter-spacing: 0.08em;
}

.version-remaining :deep(.ant-statistic-content) {
  color: var(--bluearchive-accent);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 20px color-mix(in srgb, var(--bluearchive-accent) 35%, transparent);
}

.remaining-sub {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  line-height: 1;
}

/* ---------- 无封面：简洁信息条 ---------- */
.version-info {
  padding: 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.version-info-left {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.version-info-name {
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.version-info-time {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.version-info-time-icon,
.version-info-time-label {
  color: var(--ant-color-text-secondary);
}

.version-info-time-value {
  color: var(--ant-color-text);
  font-weight: 500;
}

.version-info-right {
  flex-shrink: 0;
  text-align: right;
}

@media (max-width: 800px) {
  .version-banner {
    flex-direction: column;
    min-height: 320px;
  }

  .version-name {
    font-size: 26px;
  }

  .version-remaining {
    align-self: stretch;
    justify-content: flex-end;
    margin: 0 24px 20px;
  }

  .version-info {
    flex-direction: column;
    gap: 16px;
  }

  .version-info-right {
    text-align: left;
  }
}
</style>
