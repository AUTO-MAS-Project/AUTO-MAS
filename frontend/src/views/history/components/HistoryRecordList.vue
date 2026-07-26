<template>
  <div ref="tableWrapRef" class="log-table-wrap">
    <!-- 空状态 -->
    <EmptyState v-if="records.length === 0" class="empty-records" title="暂无记录" compact />

    <!-- 日志表格 -->
    <table v-else class="log-table">
      <thead>
        <tr>
          <th v-if="showTimestamp" class="col-time">时间</th>
          <th class="col-level">级别</th>
          <th class="col-script">脚本</th>
          <th class="col-user">用户</th>
          <th class="col-msg">消息</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(item, index) in records"
          :key="`${item.groupDate}-${item.username}-${item.record.jsonFile}`"
          class="log-row"
          :class="[`row-${item.level}`, { 'row-selected': selectedIndex === index }]"
          :data-level="item.level"
          @click="$emit('select', index, item)"
        >
          <td v-if="showTimestamp" class="col-time">
            <span class="mono-time">{{ formatTime(item.record.date) }}</span>
          </td>
          <td class="col-level">
            <span class="level-tag" :class="`tag-${item.level}`">{{ levelLabel(item.level) }}</span>
          </td>
          <td class="col-script">
            <span class="script-badge" :class="`badge-${scriptColorKey(item.script)}`">
              {{ item.script }}
            </span>
          </td>
          <td class="col-user">
            <div class="user-cell">
              <span
                class="user-avatar-xs"
                :class="{ 'user-avatar-alt': isAltAvatar(item.username) }"
              >
                {{ getAvatarInitial(item.username) }}
              </span>
              <span class="user-name">{{ item.username }}</span>
            </div>
          </td>
          <td class="col-msg" :class="{ 'col-msg--wrap': wrapText }">
            <span class="mono-msg" :class="`msg-${item.level}`">{{ buildMessage(item) }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import EmptyState from '@/components/v6/EmptyState.vue'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import type { FlatLogRecord } from '../useHistoryLogic.ts'
import { nextTick, ref, watch } from 'vue'

interface Props {
  records: FlatLogRecord[]
  selectedIndex: number
  showTimestamp: boolean
  wrapText: boolean
  autoScroll: boolean
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'select', index: number, record: FlatLogRecord): void
}>()

const tableWrapRef = ref<HTMLElement | null>(null)

const scrollToLatest = async () => {
  if (!props.autoScroll) return
  await nextTick()
  const container = tableWrapRef.value
  if (container) container.scrollTop = container.scrollHeight
}

watch(
  () => [props.records.length, props.autoScroll] as const,
  () => {
    void scrollToLatest()
  },
  { flush: 'post' }
)

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

// 仅展示 HH:MM:SS.mmm 部分（如无毫秒则补 000）
const formatTime = (date: string): string => {
  const full = formatBackendDateTime(date)
  // full 形如 "2026年07月24日 10:23:45"，取时间部分并补毫秒
  const timePart = full.includes(' ') ? full.split(' ')[1] : full
  if (!timePart) return full
  // 若已含毫秒直接返回
  if (timePart.includes('.')) return timePart
  return `${timePart}.000`
}

// 脚本徽章颜色键：按名称哈希到 blue/purple/green/orange/pink/cyan
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
.log-table-wrap {
  flex: 1;
  overflow: auto;
  background: var(--v6-color-surface);
  min-height: 0;
}

.log-table-wrap::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.log-table-wrap::-webkit-scrollbar-track {
  background: transparent;
}

.log-table-wrap::-webkit-scrollbar-thumb {
  background: var(--v6-color-border);
  border-radius: var(--v6-radius-full);
}

.log-table-wrap::-webkit-scrollbar-thumb:hover {
  background: var(--v6-color-border-strong);
}

.log-table {
  width: 100%;
  font-size: var(--v6-font-size-sm);
  border-collapse: collapse;
  table-layout: auto;
}

.log-table thead {
  position: sticky;
  top: 0;
  z-index: 2;
}

.log-table thead tr {
  background: var(--v6-vibrancy-toolbar);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.log-table th {
  text-align: left;
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text-tertiary);
  padding: var(--v6-space-1) var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border);
  user-select: none;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.log-table td {
  padding: var(--v6-space-1) var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  vertical-align: middle;
  font-size: var(--v6-font-size-sm);
  line-height: 1.6;
  height: 28px;
}

/* 列宽 */
.col-time {
  width: 132px;
  white-space: nowrap;
}

.col-level {
  width: 88px;
  white-space: nowrap;
}

.col-script {
  width: 120px;
}

.col-user {
  width: 130px;
}

.col-msg {
  min-width: 280px;
}

/* 窄容器降级:压缩各列宽度,避免记录表横向溢出
   (history-detail 容器声明于 HistoryDetailPanel 根) */
@container history-detail (max-width: 760px) {
  .col-time {
    width: 96px;
  }

  .col-level {
    width: 64px;
  }

  .col-script {
    width: 88px;
  }

  .col-user {
    width: 96px;
  }

  .col-msg {
    min-width: 160px;
  }
}

/* 等宽字体 */
.mono-time {
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.mono-msg {
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text);
  font-variant-ligatures: none;
  white-space: nowrap;
}

.col-msg--wrap .mono-msg {
  white-space: normal;
  overflow-wrap: anywhere;
}

/* 行交互 */
.log-row {
  cursor: pointer;
  transition: background-color var(--v6-motion-fast) var(--v6-ease-out);
}

.log-row:hover td {
  background: var(--v6-vibrancy-hover);
}

.log-row.row-selected td {
  background: var(--v6-vibrancy-selected);
  color: var(--v6-color-info);
}

/* 级别消息颜色 */
.row-error .mono-msg {
  color: var(--v6-color-error);
  font-weight: var(--v6-font-weight-medium);
}

.msg-error {
  font-weight: var(--v6-font-weight-medium);
}

/* 级别标签 */
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

/* 脚本徽章 */
.script-badge {
  display: inline-flex;
  align-items: center;
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-medium);
  padding: 1px var(--v6-space-2);
  border-radius: var(--v6-radius-full);
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
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

.user-name {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 空状态 */
.empty-records {
  padding: var(--v6-space-10) var(--v6-space-5);
  flex: 1;
}

:root[data-perf-mode='low'] .log-table thead tr {
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  background: var(--v6-color-surface);
}

@media (prefers-reduced-motion: reduce) {
  .log-row {
    transition: none;
  }
}
</style>
