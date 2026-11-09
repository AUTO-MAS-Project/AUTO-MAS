<script setup lang="ts">
import { computed } from 'vue'
import type { TaskRuntimeState } from '@/composables/useTaskRuntimeState'
import TaskOverviewPanel from './TaskOverviewPanel.vue'
import SchedulerLogPanel from './SchedulerLogPanel.vue'

const props = defineProps<{ runtime?: TaskRuntimeState; active: boolean; runId: string | null }>()
const resultShown = computed(
  () => props.runtime?.phase === 'completed' && Boolean(props.runtime.result)
)
const log = computed(() =>
  resultShown.value ? (props.runtime?.result ?? '') : (props.runtime?.log ?? '')
)
const firstLine = computed(() => (resultShown.value ? 1 : (props.runtime?.logFirstLine ?? 1)))
</script>

<template>
  <div class="status-container">
    <div class="overview-panel-container">
      <TaskOverviewPanel :task-info="runtime?.taskInfo ?? []" />
    </div>
    <div class="log-panel-container">
      <SchedulerLogPanel
        :log-content="log"
        :prefetch="resultShown ? null : runtime?.prefetch"
        :first-line="firstLine"
        :active="active"
        :run-id="runId"
        :external-log-mode="runtime?.phase === 'completed' ? 'browse' : 'follow'"
      />
    </div>
  </div>
</template>

<style scoped>
/* 状态容器 */
.status-container {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: var(--app-page-content-gap);
  padding: 0;
  margin: 0;
}

/* 任务总览面板容器 */
.overview-panel-container {
  flex: 0 0 33.333333%;
  /* 占据1/3宽度 */
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 日志面板容器 */
.log-panel-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

@media (max-width: 768px) {
  .status-container {
    flex-direction: column;
  }

  .overview-panel-container,
  .log-panel-container {
    flex: 1;
    width: 100%;
  }
}
</style>
