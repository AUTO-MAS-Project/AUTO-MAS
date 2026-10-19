<template>
  <div class="date-sidebar">
    <div class="sidebar-header">
      <CalendarOutlined />
      <span>{{ t('history.dateList') }}</span>
    </div>
    <div class="date-list">
      <a-collapse
        v-model:active-key="localActiveKeys"
        ghost
        accordion
        @change="handleCollapseChange"
      >
        <a-collapse-panel v-for="dateGroup in dateGroups" :key="dateGroup.date" class="date-panel">
          <template #header>
            <div class="date-header">
              <span class="date-text">{{ formatDateGroup(dateGroup.date) }}</span>
            </div>
          </template>

          <div class="user-list">
            <template v-for="group in dateGroup.groups" :key="group.script">
              <div v-if="dateGroup.groups.length > 1" class="script-label" :title="group.label">
                {{ group.label }}
              </div>
              <div
                v-for="row in group.rows"
                :key="row.key"
                class="user-item"
                :class="{ active: selectedUser === row.key }"
                @click="$emit('select-user', row.key, row.userData)"
              >
                <UserOutlined class="user-icon" />
                <span class="username">{{ row.username }}</span>
                <span class="result-counts">
                  <span
                    class="result-count success-count"
                    :class="{ 'is-zero': !row.successCount }"
                    role="img"
                    :aria-label="t('history.successCount', { count: row.successCount })"
                    :title="t('history.successCount', { count: row.successCount })"
                  >
                    <CheckOutlined aria-hidden="true" />
                    <span class="count-value" aria-hidden="true">{{ row.successCount }}</span>
                  </span>
                  <span
                    class="result-count failure-count"
                    :class="{ 'is-zero': !row.failureCount }"
                    role="img"
                    :aria-label="t('history.failureCount', { count: row.failureCount })"
                    :title="t('history.failureCount', { count: row.failureCount })"
                  >
                    <CloseOutlined aria-hidden="true" />
                    <span class="count-value" aria-hidden="true">{{ row.failureCount }}</span>
                  </span>
                </span>
                <RightOutlined class="arrow-icon" />
              </div>
            </template>
          </div>
        </a-collapse-panel>
      </a-collapse>

      <div v-if="historyData.length === 0" class="empty-sidebar">
        <img src="@/assets/NoData.png" :alt="t('history.noData')" class="empty-image" />
        <span class="empty-text">{{ t('history.empty') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { type HistoryData, HistoryIndexItem } from '@/api'
import {
  CalendarOutlined,
  CheckOutlined,
  CloseOutlined,
  RightOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'
import { formatHistoryGroupLabel } from '@/utils/dateDisplay'
import type { HistoryDateGroup } from '../useHistoryLogic.ts'

const { t } = useI18n()

interface Props {
  historyData: HistoryDateGroup[]
  activeKeys: string[]
  selectedUser: string
}

interface HistoryRow {
  key: string
  username: string
  userData: HistoryData
  successCount: number
  failureCount: number
}

interface HistoryScriptGroup {
  script: string
  label: string
  rows: HistoryRow[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:activeKeys', value: string[]): void
  (e: 'select-user', key: string, userData: HistoryData): void
}>()

const localActiveKeys = ref(props.activeKeys)

// 历史文件名是 `<托管名>-<时>-<分>-<秒>.json`；不足 4 段的（MaaFW 补前缀之前的
// 旧记录）文件名里没有托管名，返回空串
const scriptNameFromJsonFile = (jsonFile: string): string => {
  const stem = (jsonFile.split(/[\\/]/).pop() ?? '').replace(/\.json$/i, '')
  const parts = stem.split('-')
  return parts.length > 3 ? parts.slice(0, -3).join('-') : ''
}

// 历史目录按账号名分文件夹，不同托管下的同名账号会落进同一个文件夹；
// 再按文件名前缀里的托管名分一组，否则同名账号的计数会混在一起
const dateGroups = computed(() =>
  props.historyData.map(dateGroup => {
    const byScript = new Map<string, HistoryScriptGroup>()
    for (const [username, userData] of Object.entries(dateGroup.users)) {
      const buckets = new Map<string, HistoryIndexItem[]>()
      for (const record of userData.index ?? []) {
        const script = scriptNameFromJsonFile(record.jsonFile)
        const bucket = buckets.get(script)
        if (bucket) bucket.push(record)
        else buckets.set(script, [record])
      }
      if (buckets.size === 0) buckets.set('', [])

      for (const [script, records] of buckets) {
        let successCount = 0
        let failureCount = 0
        for (const record of records) {
          // 跳过（SKIP，如停服维护）既不算成功也不算失败
          if (record.status === HistoryIndexItem.status.DONE) successCount++
          else if (record.status === HistoryIndexItem.status.ERROR) failureCount++
        }
        const row: HistoryRow = {
          key: `${dateGroup.date}-${script}-${username}`,
          username,
          userData: { ...userData, index: records },
          successCount,
          failureCount,
        }
        const group = byScript.get(script)
        if (group) group.rows.push(row)
        else
          byScript.set(script, {
            script,
            label: script || t('history.scriptUnknown'),
            rows: [row],
          })
      }
    }
    return { date: dateGroup.date, groups: [...byScript.values()] }
  })
)

watch(
  () => props.activeKeys,
  val => {
    localActiveKeys.value = val
  }
)

const handleCollapseChange = (keys: string | string[]) => {
  const newKeys = Array.isArray(keys) ? keys : keys ? [keys] : []
  emit('update:activeKeys', newKeys)
}

const formatDateGroup = (date: string) => formatHistoryGroupLabel(date)
</script>

<style scoped>
.date-sidebar {
  flex: 0 0 25%;
  min-width: 200px;
  max-width: 300px;
  display: flex;
  flex-direction: column;
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.date-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

/* 滚动条样式 - 浅色 */
.date-list::-webkit-scrollbar {
  width: 8px;
}

.date-list::-webkit-scrollbar-track {
  background: transparent;
}

.date-list::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
}

.date-list::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

.date-panel {
  margin-bottom: 4px;
}

.date-panel :deep(.ant-collapse-header) {
  padding: 10px 12px !important;
  border-radius: 8px !important;
  transition: background-color 0.2s;
}

.date-panel :deep(.ant-collapse-header:hover) {
  background: var(--ant-color-fill-quaternary);
}

.date-panel :deep(.ant-collapse-content-box) {
  padding: 4px 0 !important;
}

.date-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.date-text {
  font-weight: 600;
  font-size: 14px;
  color: var(--ant-color-text);
}

.user-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 4px;
}

/* 托管分组标题：只在同一天里出现多个托管时才渲染，纯文字、不可点，不新增菜单层级 */
.script-label {
  padding: 8px 12px 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
  color: var(--ant-color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--ant-color-fill-quaternary);
}

.user-item:hover {
  background: var(--ant-color-fill-tertiary);
}

.user-item.active {
  background: var(--ant-color-primary-bg);
  border: 1px solid var(--ant-color-primary);
}

.user-icon {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}

.user-item.active .user-icon {
  color: var(--ant-color-primary);
}

.username {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 结果计数：✓/✗ 的形状本身说明成败，数字用正文色加粗，先看到数字再看图标 */
.result-counts {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 10px;
}

.result-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 34px;
  font-size: 12px;
  white-space: nowrap;
}

.count-value {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text);
}

.success-count {
  color: var(--ant-color-success);
}

.failure-count {
  color: var(--ant-color-error);
}

/* 零值不参与扫读，整体退为最弱的灰 */
.result-count.is-zero {
  color: var(--ant-color-text-quaternary);
}

.result-count.is-zero .count-value {
  font-weight: 500;
  color: inherit;
}

.arrow-icon {
  font-size: 10px;
  color: var(--ant-color-text-quaternary);
  opacity: 0;
  transition: opacity 0.2s;
}

.user-item:hover .arrow-icon,
.user-item.active .arrow-icon {
  opacity: 1;
}

.user-item.active .arrow-icon {
  color: var(--ant-color-primary);
}

.empty-sidebar {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  gap: 12px;
}

.empty-image {
  width: 80px;
  height: auto;
  opacity: 0.6;
}

.empty-text {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}
</style>

<style>
/* 深色模式滚动条 */
.dark .date-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15) !important;
}

.dark .date-list::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25) !important;
}
</style>
