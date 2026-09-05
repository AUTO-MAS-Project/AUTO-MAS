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
          <EncryptedText
            v-if="!isBootstrapping"
            :text="commandTitle"
            class="command-title"
            encrypted-class="command-title-encrypted"
            :reveal-delay-ms="66"
            :flip-delay-ms="500"
          />
        </div>
        <div v-if="!isBootstrapping" class="command-author">—— {{ commandAuthor }}</div>
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
              v-model:value="selectedTaskId"
              class="launcher-select"
              :options="schedulerTaskOptions"
              :loading="schedulerTasksLoading"
              size="large"
              :placeholder="t('home.command.placeholder')"
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
import { computed } from 'vue'
import { PlayCircleOutlined } from '@ant-design/icons-vue'
import type { ComboBoxItem } from '@/api'
import EncryptedText from '@/components/inspira/EncryptedText.vue'
import ParticlesBg from '@/components/inspira/ParticlesBg.vue'
import { useTheme } from '@/composables/useTheme'

const { t } = useI18n()

const props = defineProps<{
  isBootstrapping: boolean
  commandTitle: string
  commandAuthor: string
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

.command-title :deep(.command-title-encrypted) {
  color: var(--ant-color-text-secondary);
}

.command-author {
  position: absolute;
  right: 0;
  bottom: 0;
  z-index: 1;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
  line-height: 1.5;
  white-space: nowrap;
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
