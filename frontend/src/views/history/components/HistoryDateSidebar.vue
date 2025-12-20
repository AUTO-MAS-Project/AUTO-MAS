<template>
  <div class="date-sidebar">
    <div class="sidebar-header">
      <CalendarOutlined />
      <span>日期列表</span>
    </div>
    <div class="date-list">
      <a-collapse
        v-model:active-key="localActiveKeys"
        ghost
        accordion
        @change="handleCollapseChange"
      >
        <a-collapse-panel v-for="dateGroup in historyData" :key="dateGroup.date" class="date-panel">
          <template #header>
            <div class="date-header">
              <span class="date-text">{{ dateGroup.date }}</span>
            </div>
          </template>

          <div class="user-list">
            <div
              v-for="(userData, username) in dateGroup.users"
              :key="username"
              class="user-item"
              :class="{ active: selectedUser === `${dateGroup.date}-${username}` }"
              @click="$emit('select-user', dateGroup.date, username, userData)"
            >
              <UserOutlined class="user-icon" />
              <span class="username">{{ username }}</span>
              <RightOutlined class="arrow-icon" />
            </div>
          </div>
        </a-collapse-panel>
      </a-collapse>

      <div v-if="historyData.length === 0" class="empty-sidebar">
        <img src="../../../assets/NoData.png" alt="无数据" class="empty-image" />
        <span class="empty-text">暂无数据</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { HistoryData } from '@/api'
import { CalendarOutlined, RightOutlined, UserOutlined } from '@ant-design/icons-vue'
import { ref, watch } from 'vue'
import type { HistoryDateGroup } from '../useHistoryLogic.ts'

interface Props {
  historyData: HistoryDateGroup[]
  activeKeys: string[]
  selectedUser: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:activeKeys', value: string[]): void
  (e: 'select-user', date: string, username: string, userData: HistoryData): void
}>()

const localActiveKeys = ref(props.activeKeys)

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
  font-size: 13px;
  font-weight: 500;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
