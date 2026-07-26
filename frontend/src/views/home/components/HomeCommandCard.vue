<template>
  <a-card class="home-command-card" :bordered="false">
    <div class="command-panel">
      <div class="command-main">
        <span class="command-kicker">快速开始</span>
        <EncryptedText
          v-if="shouldAnimateTitle"
          :text="commandTitle"
          class="command-title"
          encrypted-class="command-title-encrypted"
          :reveal-delay-ms="66"
          :flip-delay-ms="500"
        />
        <h2 v-else-if="!bootstrapping" class="command-title">{{ commandTitle }}</h2>
        <p class="command-meta">
          <span>选择一个任务并启动调度</span>
        </p>
      </div>

      <div class="command-controls">
        <!-- 任务列表为空/加载失败不再单独展示警告条：
             下方禁用的下拉（placeholder「任务列表不可用」）已表达该状态，
             重取能力保留在页头「刷新」按钮与下拉展开时的自动重新拉取 -->
        <a-alert
          v-if="startError"
          class="command-error"
          type="error"
          show-icon
          :message="startError"
        >
          <template #action>
            <a-button size="small" :loading="starting" @click="$emit('retry-start')">
              重试启动
            </a-button>
          </template>
        </a-alert>
        <a-select
          v-model:value="selectedTaskId"
          class="command-select"
          :options="taskOptions"
          :loading="tasksLoading"
          :popup-match-select-width="false"
          :title="selectedTaskLabel"
          size="large"
          :placeholder="tasksError ? '任务列表不可用' : '选择任务'"
          :disabled="Boolean(tasksError) || starting"
          @dropdown-visible-change="onDropdownVisibleChange"
        >
          <template #option="{ label, title }">
            <span class="command-task-option" :title="String(title || label)">
              {{ label }}
            </span>
          </template>
        </a-select>
        <a-select
          v-model:value="selectedMode"
          class="command-mode"
          :options="modeOptions"
          size="large"
          :disabled="Boolean(tasksError) || starting || !selectedTaskId || modeOptions.length === 0"
        />
        <a-button
          type="primary"
          size="large"
          class="command-start"
          :loading="starting"
          :disabled="!selectedTaskId || Boolean(tasksError)"
          @click="onStart"
        >
          <template #icon>
            <PlayCircleOutlined />
          </template>
          开始
        </a-button>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { PlayCircleOutlined } from '@ant-design/icons-vue'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import EncryptedText from '@/components/inspira/EncryptedText.vue'
import { useLowPerfMode } from '@/composables/useLowPerfMode'
import type { HomeTaskModeOption, HomeTaskOption } from '../useHomeLogic'

interface Props {
  commandTitle: string
  bootstrapping: boolean
  taskOptions: HomeTaskOption[]
  modeOptions: HomeTaskModeOption[]
  tasksLoading: boolean
  tasksError: string | null
  starting: boolean
  startError: string | null
  selectedTaskId: string | null
  selectedMode: TaskCreateIn.mode
}

const props = defineProps<Props>()
const { isLowPerf } = useLowPerfMode()
const prefersReducedMotion = ref(false)
let reducedMotionQuery: MediaQueryList | null = null

const syncReducedMotion = (event: MediaQueryListEvent) => {
  prefersReducedMotion.value = event.matches
}

onMounted(() => {
  if (typeof window.matchMedia !== 'function') return
  try {
    reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    prefersReducedMotion.value = reducedMotionQuery.matches
    reducedMotionQuery.addEventListener?.('change', syncReducedMotion)
  } catch {
    reducedMotionQuery = null
  }
})

onUnmounted(() => {
  reducedMotionQuery?.removeEventListener?.('change', syncReducedMotion)
  reducedMotionQuery = null
})

const shouldAnimateTitle = computed(
  () => !props.bootstrapping && !isLowPerf.value && !prefersReducedMotion.value
)

const emit = defineEmits<{
  (e: 'update:selectedTaskId', value: string | null): void
  (e: 'update:selectedMode', value: TaskCreateIn.mode): void
  (e: 'dropdown-visible-change', open: boolean): void
  (e: 'retry-start'): void
  (e: 'start'): void
}>()

const selectedTaskId = computed({
  get: () => props.selectedTaskId,
  set: value => emit('update:selectedTaskId', value),
})

const selectedTaskLabel = computed(
  () => props.taskOptions.find(option => option.value === props.selectedTaskId)?.label || ''
)

const selectedMode = computed({
  get: () => props.selectedMode,
  set: value => emit('update:selectedMode', value),
})

const onDropdownVisibleChange = (open: boolean) => {
  emit('dropdown-visible-change', open)
}

const onStart = () => {
  emit('start')
}
</script>

<style scoped>
.home-command-card {
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-content);
  border: 1px solid var(--v6-color-border-subtle);
  box-shadow: var(--v6-shadow-xs);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.command-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--v6-space-6);
  align-items: center;
}

.command-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
}

.command-kicker {
  width: fit-content;
  font-size: 12px;
  font-weight: 600;
  color: var(--v6-color-primary);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.command-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.25;
  color: var(--v6-color-text);
}

.command-title :deep(.command-title-encrypted) {
  color: var(--v6-color-text-secondary);
}

.command-meta {
  margin: 0;
  font-size: 13px;
  color: var(--v6-color-text-secondary);
}

.command-controls {
  width: min(720px, 100%);
  min-width: 560px;
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 132px 112px;
  gap: var(--v6-space-3);
  align-items: center;
}

.command-error {
  grid-column: 1 / -1;
}

.command-select,
.command-mode,
.command-start {
  width: 100%;
}

@container home-layout (max-width: 1024px) {
  .command-panel {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .command-controls {
    min-width: 0;
  }
}

@container home-layout (max-width: 640px) {
  .command-controls {
    grid-template-columns: 1fr;
  }
}

:root[data-perf-mode='low'] .command-title {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .command-title {
    transition: none;
  }
}
</style>
