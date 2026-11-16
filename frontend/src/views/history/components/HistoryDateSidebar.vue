<template>
  <div class="date-sidebar">
    <div class="sidebar-header">
      <CalendarOutlined />
      <span>{{ t('core.history.dateList') }}</span>
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
                    :aria-label="t('core.history.successCount', { count: row.successCount })"
                    :title="t('core.history.successCount', { count: row.successCount })"
                  >
                    <CheckOutlined aria-hidden="true" />
                    <span class="count-value" aria-hidden="true">{{ row.successCount }}</span>
                  </span>
                  <span
                    class="result-count failure-count"
                    :class="{ 'is-zero': !row.failureCount }"
                    role="img"
                    :aria-label="t('core.history.failureCount', { count: row.failureCount })"
                    :title="t('core.history.failureCount', { count: row.failureCount })"
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
        <NoData :image-style="{ height: '80px' }" :description="t('core.history.empty')" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { HistoryBucket } from '@/api'
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

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:activeKeys', value: string[]): void
  (e: 'select-user', key: string, userData: HistoryBucket): void
}>()

const localActiveKeys = ref(props.activeKeys)

// 日期和用户名沿用后端分组；托管名称在记录元数据中展示。
const dateGroups = computed(() =>
  props.historyData.map(dateGroup => ({
    date: dateGroup.date,
    groups: [
      {
        script: '',
        label: '',
        rows: Object.entries(dateGroup.users).map(([username, userData]) => ({
          key: JSON.stringify([dateGroup.date, username]),
          username,
          userData,
          successCount: (userData.index ?? []).filter(record => record.status === 'success').length,
          failureCount: (userData.index ?? []).filter(record => record.status === 'error').length,
        })),
      },
    ],
  }))
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
</style>
