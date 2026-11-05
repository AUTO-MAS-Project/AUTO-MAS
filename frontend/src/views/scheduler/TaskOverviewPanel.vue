<template>
  <div class="scheduler-panel overview-panel">
    <div class="scheduler-panel-header">
      <h3>{{ t('core.scheduler.overview.title') }}</h3>
      <!--      <a-badge :count="totalTaskCount" :overflow-count="99" />-->
    </div>
    <div class="overview-content">
      <TaskTree :task-data="taskData" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TaskTree from '@/components/TaskTree.vue'
import type { WSTaskScriptInfoData } from '@/services/websocket/types'

const props = defineProps<{ taskInfo: WSTaskScriptInfoData[] }>()
const { t } = useI18n()
const taskData = computed(() =>
  props.taskInfo.map(script => ({
    ...script,
    name: script.name || t('core.scheduler.overview.unknownScript'),
    user_list: script.userList,
  }))
)
</script>

<style scoped src="./schedulerPanel.css"></style>

<style scoped>
.scheduler-panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.overview-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* 滚动条样式 - 浅色 */
.overview-content::-webkit-scrollbar {
  width: 8px;
}

.overview-content::-webkit-scrollbar-track {
  background: transparent;
}

.overview-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
}

.overview-content::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

@media (max-width: 768px) {
  .overview-panel {
    border-radius: 8px;
  }

  .scheduler-panel-header {
    padding: 12px;
  }
}
</style>

<style>
/* 深色模式滚动条 - 需要全局样式 */
.dark .overview-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15) !important;
}

.dark .overview-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25) !important;
}
</style>
