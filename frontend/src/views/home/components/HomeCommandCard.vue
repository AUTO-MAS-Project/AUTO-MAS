<template>
  <a-card class="command-card">
    <section class="command-panel" :aria-label="t('home.command.aria')">
      <div class="command-main">
        <ParticlesBg
          class="command-particles"
          :color="commandParticleColor"
          :ease="65"
          :quantity="128"
          :staticity="70"
        />
        <div class="command-content">
          <ShatterText v-if="!isBootstrapping" :text="commandTitle" class="command-title" />
        </div>
        <div v-if="!isBootstrapping" class="command-footer">
          <a-tooltip :title="t('home.command.refresh')">
            <a-button
              type="text"
              size="small"
              class="command-refresh"
              :aria-label="t('home.command.refresh')"
              @click="onRefreshGreeting"
            >
              <template #icon>
                <ReloadOutlined :key="spinKey" class="command-refresh-icon" />
              </template>
            </a-button>
          </a-tooltip>
          <span class="command-author">—— {{ commandAuthor }}</span>
        </div>
      </div>

      <div class="scheduler-launcher">
        <ParticlesBg
          class="scheduler-particles"
          :color="commandParticleColor"
          :ease="65"
          :quantity="128"
          :staticity="70"
        />
        <div class="scheduler-content">
          <div class="launcher-header">
            <div>
              <div class="launcher-title">{{ t('home.command.title') }}</div>
            </div>
          </div>

          <div class="launcher-controls">
            <a-select
              v-model:value="selectedTaskIds"
              class="launcher-select"
              mode="multiple"
              :options="schedulerTaskOptions"
              :loading="schedulerTasksLoading"
              size="large"
              :max-tag-count="'responsive'"
              :placeholder="t('home.command.placeholder')"
              @dropdown-visible-change="$emit('dropdown-visible-change', $event)"
            >
              <!-- 拉取失败时列表为空：说明原因，展开下拉本身就会重试 -->
              <template v-if="schedulerTasksUnavailable" #notFoundContent>
                <span class="launcher-select-hint">{{ t('home.quickStart.listUnavailable') }}</span>
              </template>
            </a-select>
            <a-button
              type="primary"
              size="large"
              class="launcher-start"
              :loading="startingHomeTask"
              :disabled="schedulerTasksLoading || selectedTaskIds.length === 0"
              @click="$emit('start')"
            >
              <template #icon>
                <PlayCircleOutlined />
              </template>
              {{ t('home.command.start') }}
            </a-button>
          </div>
        </div>
      </div>
    </section>
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { ComboBoxItem } from '@/api'
import ParticlesBg from '@/components/inspira/ParticlesBg.vue'
import { useTheme } from '@/composables/useTheme'
import ShatterText from '@/views/home/components/ShatterText.vue'

const { t } = useI18n()

const props = defineProps<{
  isBootstrapping: boolean
  commandTitle: string
  commandAuthor: string
  schedulerTaskOptions: ComboBoxItem[]
  schedulerTasksLoading: boolean
  schedulerTasksUnavailable: boolean
  startingHomeTask: boolean
  selectedTaskIds: string[]
}>()

const emit = defineEmits<{
  'update:selectedTaskIds': [value: string[]]
  'dropdown-visible-change': [open: boolean]
  start: []
  'refresh-greeting': []
}>()

// 靠 key 变化重挂载图标来重放旋转动画，比手动增删 class 稳
const spinKey = ref(0)

const onRefreshGreeting = () => {
  spinKey.value += 1
  emit('refresh-greeting')
}

const selectedTaskIds = computed({
  get: () => props.selectedTaskIds,
  set: value => emit('update:selectedTaskIds', value),
})

const { themeColor, themeColors } = useTheme()
const commandParticleColor = computed(() => themeColors[themeColor.value])
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
  position: relative;
  padding-bottom: 24px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  border-radius: 6px;
  isolation: isolate;
}

.command-particles {
  z-index: 0;
  opacity: 1;
}

.command-content {
  position: relative;
  z-index: 1;
}

.command-title {
  font-size: 30px;
  line-height: 1.2;
  font-weight: 700;
  color: var(--ant-color-text);
}

.command-footer {
  position: absolute;
  right: 0;
  bottom: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 4px;
}

.command-author {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
  line-height: 1.5;
  white-space: nowrap;
}

.command-refresh {
  color: var(--ant-color-text-tertiary);
  transition: color 0.2s ease;
}

.command-refresh:hover {
  color: var(--ant-color-primary);
}

.command-refresh-icon {
  animation: command-refresh-spin 0.5s ease;
}

@keyframes command-refresh-spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

.scheduler-launcher {
  min-width: 0;
  position: relative;
  padding: 0 0 0 24px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  border-radius: 6px;
  isolation: isolate;
  border-left: 1px solid var(--ant-color-border);
}

.scheduler-particles {
  z-index: 0;
  opacity: 1;
}

.scheduler-content {
  position: relative;
  z-index: 1;
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

.launcher-select-hint {
  color: var(--ant-color-text-tertiary);
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
