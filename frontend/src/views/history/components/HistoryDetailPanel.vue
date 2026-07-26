<template>
  <div class="detail-panel">
    <!-- 主日志内容区 -->
    <main class="log-content-area">
      <!-- 子工具栏：筛选 chips + 切换按钮 -->
      <div class="log-subtoolbar">
        <div class="filter-chips" role="region" aria-label="当前筛选条件">
          <span
            v-for="chip in activeFilterChips"
            :key="chip.key"
            class="filter-chip"
            :class="{ 'chip-error-tone': chip.tone === 'error' }"
          >
            <span class="chip-key">{{ chip.label }}</span>
            <span class="chip-value" :class="{ 'chip-value-error': chip.tone === 'error' }">
              {{ chip.value }}
            </span>
            <button
              class="chip-remove"
              type="button"
              :aria-label="`移除筛选 ${chip.label}`"
              @click="$emit('remove-chip', chip.key)"
            >
              <CloseOutlined class="chip-x" />
            </button>
          </span>
          <span v-if="activeFilterChips.length === 0" class="chips-empty">无激活筛选</span>
        </div>

        <div class="log-toggles">
          <button
            class="toggle-btn"
            type="button"
            :aria-pressed="showTimestamp"
            :title="showTimestamp ? '隐藏时间戳' : '显示时间戳'"
            @click="$emit('update:show-timestamp', !showTimestamp)"
          >
            <ClockCircleOutlined class="toggle-icon" />
            <span>时间戳</span>
          </button>
          <button
            class="toggle-btn"
            type="button"
            :aria-pressed="wrapText"
            :title="wrapText ? '关闭自动换行' : '开启自动换行'"
            @click="$emit('update:wrap-text', !wrapText)"
          >
            <AlignLeftOutlined class="toggle-icon" />
            <span>换行</span>
          </button>
          <button
            class="toggle-btn"
            type="button"
            :aria-pressed="liveRefresh"
            :title="liveRefresh ? '暂停实时刷新' : '继续实时刷新'"
            @click="$emit('update:live-refresh', !liveRefresh)"
          >
            <ReloadOutlined class="toggle-icon" :class="{ 'toggle-spin': liveRefresh }" />
            <span>{{ liveRefresh ? '实时' : '已暂停' }}</span>
          </button>
        </div>
      </div>

      <!-- 日志表格 -->
      <HistoryRecordList
        :records="records"
        :selected-index="selectedRecordIndex"
        :show-timestamp="showTimestamp"
        :wrap-text="wrapText"
        :auto-scroll="autoScroll"
        @select="(index, record) => $emit('select-record', index, record)"
      />

      <!-- 底部状态栏 -->
      <div class="log-bottombar">
        <div class="bottombar-left">
          <span class="log-count">显示 {{ records.length.toLocaleString() }} 条记录</span>
          <span class="bottombar-sep" />
          <span class="log-count-sub">共 {{ totalCount.toLocaleString() }} 条</span>
        </div>
        <div class="bottombar-right">
          <label class="toggle-label">
            <input
              type="checkbox"
              class="autoscroll-check"
              :checked="autoScroll"
              @change="$emit('update:auto-scroll', ($event.target as HTMLInputElement).checked)"
            />
            <span class="toggle-switch" />
            <span class="toggle-text">自动滚动</span>
          </label>
        </div>
      </div>
    </main>

    <!-- Inspector 详情面板 -->
    <aside v-if="inspectorVisible" class="inspector-panel" aria-label="日志详情">
      <div class="inspector-header">
        <span class="inspector-title">详情</span>
        <div class="inspector-actions">
          <button
            v-if="selectedRecordDetail"
            class="inspector-action-btn"
            type="button"
            aria-label="查看完整日志"
            title="查看完整日志"
            @click="$emit('view-full-log')"
          >
            <FileTextOutlined class="inspector-action-icon" />
          </button>
          <button
            class="inspector-close"
            type="button"
            aria-label="关闭详情面板"
            @click="$emit('close-inspector')"
          >
            <CloseOutlined class="inspector-close-icon" />
          </button>
        </div>
      </div>

      <!-- 无选中记录时的空状态 -->
      <EmptyState
        v-if="!selectedRecordDetail"
        class="inspector-empty"
        title="未选择记录"
        description="点击日志行以查看详情"
        compact
      />

      <div v-else class="inspector-body">
        <div class="inspector-section">
          <div class="inspector-label">级别</div>
          <div class="inspector-value">
            <span class="level-tag" :class="`tag-${selectedRecordDetail.level}`">
              {{ levelLabel(selectedRecordDetail.level) }}
            </span>
          </div>
        </div>

        <div class="inspector-section">
          <div class="inspector-label">时间</div>
          <div class="inspector-value mono-text">
            {{ formatFullTime(selectedRecordDetail.record.date) }}
          </div>
        </div>

        <div class="inspector-section">
          <div class="inspector-label">脚本</div>
          <div class="inspector-value">
            <span
              class="script-badge"
              :class="`badge-${scriptColorKey(selectedRecordDetail.script)}`"
            >
              {{ selectedRecordDetail.script }}
            </span>
          </div>
        </div>

        <div class="inspector-section">
          <div class="inspector-label">用户</div>
          <div class="inspector-value">
            <div class="user-cell">
              <span
                class="user-avatar-xs"
                :class="{ 'user-avatar-alt': isAltAvatar(selectedRecordDetail.username) }"
              >
                {{ getAvatarInitial(selectedRecordDetail.username) }}
              </span>
              <span>{{ selectedRecordDetail.username }}</span>
            </div>
          </div>
        </div>

        <div class="inspector-section inspector-section--full">
          <div class="inspector-label">消息</div>
          <div
            class="inspector-value msg-detail"
            :class="`msg-detail-${selectedRecordDetail.level}`"
          >
            {{ buildMessage(selectedRecordDetail) }}
          </div>
        </div>

        <!-- 统计信息（仅在选中记录所属用户有统计数据时展示） -->
        <div v-if="hasStatistics" class="inspector-section inspector-section--full">
          <div class="inspector-label">统计</div>
          <div class="inspector-value">
            <UserStatisticsCard
              :recruit-statistics="recruitStatistics"
              :drop-statistics="dropStatistics"
              compact
            />
          </div>
        </div>

        <!-- 堆栈跟踪 / 错误详情 -->
        <div
          v-if="selectedRecordDetail.errorMessage"
          class="inspector-section inspector-section--full"
        >
          <div class="inspector-label">错误详情</div>
          <pre class="stack-trace mono-text">{{ selectedRecordDetail.errorMessage }}</pre>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import {
  AlignLeftOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  FileTextOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { computed } from 'vue'
import EmptyState from '@/components/v6/EmptyState.vue'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import HistoryRecordList from './HistoryRecordList.vue'
import UserStatisticsCard from './UserStatisticsCard.vue'
import type { FlatLogRecord } from '../useHistoryLogic.ts'

interface FilterChip {
  key: string
  label: string
  value: string
  tone?: 'error' | 'info'
}

interface Props {
  records: FlatLogRecord[]
  selectedRecordIndex: number
  activeFilterChips: FilterChip[]
  showTimestamp: boolean
  wrapText: boolean
  liveRefresh: boolean
  autoScroll: boolean
  selectedRecordDetail: FlatLogRecord | null
  inspectorVisible: boolean
  recruitStatistics: Record<string, number> | null
  dropStatistics: Record<string, Record<string, number>> | null
  totalCount: number
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'select-record', index: number, record: FlatLogRecord): void
  (e: 'remove-chip', key: string): void
  (e: 'update:show-timestamp', value: boolean): void
  (e: 'update:wrap-text', value: boolean): void
  (e: 'update:live-refresh', value: boolean): void
  (e: 'update:auto-scroll', value: boolean): void
  (e: 'close-inspector'): void
  (e: 'view-full-log'): void
}>()

const hasStatistics = computed(() => {
  const r = props.recruitStatistics
  const d = props.dropStatistics
  const hasR = r && Object.keys(r).length > 0
  const hasD = d && Object.keys(d).length > 0
  return Boolean(hasR || hasD)
})

const levelLabel = (level: FlatLogRecord['level']): string => {
  switch (level) {
    case 'error':
      return 'ERROR'
    case 'info':
      return 'INFO'
    default:
      return String(level).toUpperCase()
  }
}

const formatFullTime = (date: string): string => {
  return formatBackendDateTime(date)
}

const scriptColorKey = (name: string): string => {
  const keys = ['blue', 'purple', 'green', 'orange', 'pink', 'cyan']
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return keys[hash % keys.length]
}

const buildMessage = (item: FlatLogRecord): string => {
  if (item.level === 'error' && item.errorMessage) {
    return item.errorMessage
  }
  const status = item.record.status
  if (status === 'DONE' || status === 'SUCCESS') {
    return `任务执行完成 (${item.record.jsonFile.split('/').pop() ?? item.record.jsonFile})`
  }
  if (item.level === 'error') {
    return `执行失败: ${item.errorMessage || item.record.status}`
  }
  return `任务记录: ${item.record.jsonFile.split('/').pop() ?? item.record.jsonFile}`
}

const getAvatarInitial = (name: string): string => {
  if (!name) return '?'
  return name.charAt(0).toUpperCase()
}

const isAltAvatar = (name: string): boolean => {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return hash % 2 === 1
}
</script>

<style scoped>
.detail-panel {
  container: history-detail / inline-size;
  flex: 1;
  display: flex;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

/* ═══════════════════════════════════════════════════════════
   主日志内容区
   ═══════════════════════════════════════════════════════════ */
.log-content-area {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--v6-color-surface);
}

/* ── 子工具栏 ─────────────────────────────────────────── */
.log-subtoolbar {
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--v6-space-3);
  background: var(--v6-vibrancy-content);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  border-bottom: 1px solid var(--v6-color-border);
  gap: var(--v6-space-3);
}

.filter-chips {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}

.filter-chips::-webkit-scrollbar {
  display: none;
}

.chips-empty {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
  font-style: italic;
  white-space: nowrap;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--v6-space-1);
  height: 22px;
  padding: 0 var(--v6-space-1) 0 var(--v6-space-2);
  background: var(--v6-color-info-bg);
  border-radius: var(--v6-radius-xs);
  font-size: var(--v6-font-size-sm);
  white-space: nowrap;
  flex-shrink: 0;
}

.chip-key {
  color: var(--v6-color-text-tertiary);
  font-weight: var(--v6-font-weight-medium);
}

.chip-value {
  color: var(--v6-color-info);
  font-weight: var(--v6-font-weight-semibold);
}

.chip-value-error {
  color: var(--v6-color-error);
}

.chip-error-tone {
  background: var(--v6-color-error-bg);
}

.chip-remove {
  width: 16px;
  height: 16px;
  border-radius: var(--v6-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v6-color-text-tertiary);
  transition:
    background-color var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out);
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
}

.chip-remove:hover {
  background: var(--v6-vibrancy-hover);
  color: var(--v6-color-text);
}

.chip-x {
  font-size: 10px;
}

/* ── 切换按钮 ─────────────────────────────────────────── */
.log-toggles {
  display: flex;
  align-items: center;
  gap: var(--v6-space-0-5);
  flex-shrink: 0;
}

.toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--v6-space-1);
  height: 22px;
  padding: 0 var(--v6-space-2);
  border-radius: var(--v6-radius-xs);
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-tertiary);
  transition:
    color var(--v6-motion-fast) var(--v6-ease-out),
    background-color var(--v6-motion-fast) var(--v6-ease-out);
  border: none;
  background: transparent;
  cursor: pointer;
}

.toggle-btn:hover {
  background: var(--v6-vibrancy-hover);
  color: var(--v6-color-text);
}

.toggle-btn[aria-pressed='true'] {
  color: var(--v6-color-info);
  background: var(--v6-color-info-bg);
}

.toggle-icon {
  font-size: 12px;
}

.toggle-spin {
  animation: gentle-spin 3s linear infinite;
}

@keyframes gentle-spin {
  to {
    transform: rotate(360deg);
  }
}

/* ── 底部状态栏 ───────────────────────────────────────── */
.log-bottombar {
  min-height: 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--v6-space-3);
  background: var(--v6-vibrancy-content);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  border-top: 1px solid var(--v6-color-border);
  font-size: var(--v6-font-size-sm);
}

.bottombar-left {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  color: var(--v6-color-text-tertiary);
}

.log-count {
  font-variant-numeric: tabular-nums;
}

.log-count-sub {
  color: var(--v6-color-text-quaternary);
}

.bottombar-sep {
  width: 1px;
  height: 12px;
  background: var(--v6-color-border);
}

.bottombar-right {
  display: flex;
  align-items: center;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
  cursor: pointer;
  user-select: none;
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text);
}

.autoscroll-check {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}

.toggle-switch {
  width: 32px;
  height: 20px;
  border-radius: var(--v6-radius-full);
  background: var(--v6-color-border-strong);
  position: relative;
  transition: background-color var(--v6-motion-fast) var(--v6-ease-out);
}

.toggle-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--v6-color-surface-elevated);
  box-shadow: var(--v6-shadow-xs);
  transition: transform var(--v6-motion-fast) var(--v6-ease-out);
}

.autoscroll-check:checked + .toggle-switch {
  background: var(--v6-color-info);
}

.autoscroll-check:checked + .toggle-switch::after {
  transform: translateX(12px);
}

.autoscroll-check:focus-visible + .toggle-switch {
  outline: var(--v6-outline-width) solid var(--v6-color-info);
  outline-offset: var(--v6-focus-ring-offset);
}

.toggle-text {
  color: var(--v6-color-text-tertiary);
}

/* ═══════════════════════════════════════════════════════════
   Inspector 面板
   ═══════════════════════════════════════════════════════════ */
.inspector-panel {
  width: 300px;
  min-width: 300px;
  background: var(--v6-vibrancy-sidebar);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  border-left: 1px solid var(--v6-color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.inspector-header {
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border);
  flex-shrink: 0;
}

.inspector-title {
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

.inspector-actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-0-5);
}

.inspector-action-btn,
.inspector-close {
  width: 22px;
  height: 22px;
  border-radius: var(--v6-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v6-color-text-tertiary);
  transition:
    background-color var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out);
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
}

.inspector-action-btn:hover,
.inspector-close:hover {
  background: var(--v6-vibrancy-hover);
  color: var(--v6-color-text);
}

.inspector-action-icon,
.inspector-close-icon {
  font-size: 12px;
}

.inspector-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--v6-space-3);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--v6-space-3) var(--v6-space-4);
  align-content: start;
}

/* Inspector 空状态 */
.inspector-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.inspector-body::-webkit-scrollbar {
  width: 8px;
}

.inspector-body::-webkit-scrollbar-track {
  background: transparent;
}

.inspector-body::-webkit-scrollbar-thumb {
  background: var(--v6-color-border);
  border-radius: var(--v6-radius-full);
}

.inspector-body::-webkit-scrollbar-thumb:hover {
  background: var(--v6-color-border-strong);
}

.inspector-section {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-1);
}

.inspector-section--full {
  grid-column: 1 / -1;
}

.inspector-label {
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.inspector-value {
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text);
  word-break: break-all;
}

.mono-text {
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-xs);
  font-variant-numeric: tabular-nums;
}

.msg-detail {
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-xs);
  padding: var(--v6-space-2) var(--v6-space-3);
  background: var(--v6-color-error-bg);
  border-radius: var(--v6-radius-xs);
  border: 1px solid var(--v6-color-error-border);
  color: var(--v6-color-error);
  line-height: 1.5;
  white-space: pre-wrap;
}

.msg-detail-info {
  background: var(--v6-color-info-bg);
  border-color: var(--v6-color-info-border);
  color: var(--v6-color-info);
}

.stack-trace {
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-xs);
  line-height: 1.7;
  padding: var(--v6-space-3);
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-xs);
  border: 1px solid var(--v6-color-border);
  color: var(--v6-color-text);
  overflow-x: auto;
  white-space: pre;
  margin: 0;
  max-height: 240px;
  overflow-y: auto;
}

/* 级别标签（与日志表格一致） */
.level-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--v6-font-mono);
  font-size: 10px;
  font-weight: var(--v6-font-weight-bold);
  letter-spacing: 0.03em;
  padding: 1px var(--v6-space-1);
  border-radius: var(--v6-radius-xs);
  line-height: 1.5;
}

.tag-error {
  background: var(--v6-color-error-bg);
  color: var(--v6-color-error);
}

.tag-info {
  background: var(--v6-color-info-bg);
  color: var(--v6-color-info);
}

/* 脚本徽章（与日志表格一致） */
.script-badge {
  display: inline-flex;
  align-items: center;
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-medium);
  padding: 1px var(--v6-space-2);
  border-radius: var(--v6-radius-full);
  white-space: nowrap;
}

.badge-blue {
  background: var(--v6-color-info-bg);
  color: var(--v6-color-info);
}

.badge-purple {
  background: color-mix(in srgb, #af52de 12%, transparent);
  color: #af52de;
}

.badge-green {
  background: var(--v6-color-success-bg);
  color: var(--v6-color-success);
}

.badge-orange {
  background: var(--v6-color-warning-bg);
  color: var(--v6-color-warning);
}

.badge-pink {
  background: color-mix(in srgb, #ff375f 12%, transparent);
  color: #ff375f;
}

.badge-cyan {
  background: color-mix(in srgb, #5ac8fa 12%, transparent);
  color: #5ac8fa;
}

/* 用户单元格 */
.user-cell {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
}

.user-avatar-xs {
  width: 18px;
  height: 18px;
  border-radius: var(--v6-radius-full);
  background: linear-gradient(135deg, var(--v6-color-info) 0%, #5ac8fa 100%);
  color: var(--v6-color-text-inverse);
  font-size: 9px;
  font-weight: var(--v6-font-weight-semibold);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.user-avatar-alt {
  background: linear-gradient(135deg, var(--v6-color-warning) 0%, var(--v6-color-error) 100%);
}

/* 低性能模式 */
:root[data-perf-mode='low'] .log-subtoolbar,
:root[data-perf-mode='low'] .log-bottombar,
:root[data-perf-mode='low'] .inspector-panel {
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  background: var(--v6-color-surface);
}

@media (prefers-reduced-motion: reduce) {
  .toggle-btn,
  .chip-remove,
  .inspector-close,
  .toggle-switch,
  .toggle-switch::after {
    transition: none;
  }

  .toggle-spin {
    animation: none;
  }
}

/* 响应式：窄屏隐藏 Inspector */
@container history-detail (max-width: 1100px) {
  .inspector-panel {
    display: none;
  }
}
</style>
