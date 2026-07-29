<template>
  <a-card class="command-card">
    <section class="command-panel" aria-label="调度快速启动">
      <div class="command-main">
        <EncryptedText
          v-if="!isBootstrapping"
          :text="commandTitle"
          class="command-title"
          encrypted-class="command-title-encrypted"
          :reveal-delay-ms="66"
          :flip-delay-ms="500"
        />
      </div>

      <div class="scheduler-launcher">
        <div class="launcher-header">
          <div>
            <div class="launcher-title">快速开始</div>
          </div>
        </div>

        <div class="launcher-controls">
          <a-select
            v-model:value="selectedTaskId"
            class="launcher-select"
            :options="schedulerTaskOptions"
            :loading="schedulerTasksLoading"
            size="large"
            placeholder="选择任务"
            @dropdown-visible-change="$emit('dropdown-visible-change', $event)"
          />
          <a-button
            type="primary"
            size="large"
            class="launcher-start"
            :loading="startingHomeTask"
            :disabled="!selectedTaskId"
            @click="$emit('start')"
          >
            <template #icon>
              <PlayCircleOutlined />
            </template>
            开始
          </a-button>
        </div>
      </div>
    </section>
  </a-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { PlayCircleOutlined } from '@ant-design/icons-vue'
import type { ComboBoxItem } from '@/api'
import EncryptedText from '@/components/inspira/EncryptedText.vue'

const props = defineProps<{
  isBootstrapping: boolean
  commandTitle: string
  schedulerTaskOptions: ComboBoxItem[]
  schedulerTasksLoading: boolean
  startingHomeTask: boolean
  selectedTaskId: string | null
}>()

const emit = defineEmits<{
  'update:selectedTaskId': [value: string | null]
  'dropdown-visible-change': [open: boolean]
  start: []
}>()

const selectedTaskId = computed({
  get: () => props.selectedTaskId,
  set: value => emit('update:selectedTaskId', value),
})
</script>

<style scoped>
.command-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.command-card :deep(.ant-card-body) {
  padding: 24px;
}

.command-panel {
  min-height: 148px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 24px;
  color: var(--ant-color-text);
}

.command-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.command-title {
  font-size: 30px;
  line-height: 1.2;
  font-weight: 700;
  color: var(--ant-color-text);
}

.command-title :deep(.command-title-encrypted) {
  color: var(--ant-color-text-secondary);
}

.scheduler-launcher {
  min-width: 0;
  padding: 0 0 0 24px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border-left: 1px solid var(--ant-color-border);
}

.launcher-header {
  margin-bottom: 18px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.launcher-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.launcher-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 112px;
  gap: 12px;
}

.launcher-select,
.launcher-start {
  width: 100%;
}

@media (max-width: 1240px) {
  .command-panel {
    grid-template-columns: 1fr;
  }

  .scheduler-launcher {
    max-width: 100%;
    padding: 18px 0 0;
    border-left: none;
    border-top: 1px solid var(--ant-color-border);
  }
}

@media (max-width: 800px) {
  .command-card :deep(.ant-card-body) {
    padding: 18px;
  }

  .command-title {
    font-size: 24px;
  }
}

@media (max-width: 560px) {
  .launcher-controls {
    grid-template-columns: 1fr;
  }
}
</style>
