<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { QueueConfig_Cycle, QueueUpdateIn } from '@/api'
import { queueApi } from '@/composables/useQueueApi'
import dayjs from 'dayjs'

const props = defineProps<{ queueId: string; cycle?: QueueConfig_Cycle | null }>()
const emit = defineEmits<{ refresh: [] }>()
const { t } = useI18n()
const interval = ref<number | null>(480)
const saving = ref(false)

watch(
  () => props.cycle,
  () => {
    interval.value = props.cycle?.IntervalMinutes ?? 480
  },
  { immediate: true }
)

async function save(data: NonNullable<QueueUpdateIn['data']['Cycle']>) {
  saving.value = true
  try {
    const response = await queueApi.updateQueue({ queueId: props.queueId, data: { Cycle: data } })
    if (response.code !== 200) throw new Error(response.message)
  } catch (error) {
    message.error(error instanceof Error ? error.message : String(error))
  } finally {
    saving.value = false
    emit('refresh')
  }
}

function saveInterval() {
  if (
    interval.value === null ||
    !Number.isInteger(interval.value) ||
    interval.value < 1 ||
    interval.value > 10080
  ) {
    interval.value = props.cycle?.IntervalMinutes ?? 480
    return
  }
  if (interval.value !== props.cycle?.IntervalMinutes)
    void save({ IntervalMinutes: interval.value })
}
</script>

<template>
  <a-card :title="t('core.queue.triggers.cycleSettings')" class="queue-cycle-settings">
    <a-form layout="vertical" :disabled="saving">
      <a-row :gutter="[24, 0]">
        <a-col :xs="24" :sm="12" :xl="6">
          <a-form-item :label="t('core.queue.triggers.interval')">
            <a-input-number
              v-model:value="interval"
              size="large"
              :min="1"
              :max="10080"
              :precision="0"
              :addon-after="t('core.queue.cycle.minuteUnit')"
              style="width: 100%"
              @blur="saveInterval"
              @press-enter="saveInterval"
            />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :sm="12" :xl="6">
          <a-form-item :label="t('core.queue.cycle.nextRun')">
            <div class="cycle-next-run">
              <output class="cycle-next-run-time" :aria-label="t('core.queue.cycle.nextRun')">{{
                cycle?.NextRunAt ? dayjs(cycle.NextRunAt).format('YYYY-MM-DD HH:mm') : '—'
              }}</output>
              <a-button size="large" :loading="saving" @click="save({ ResetTimer: true })">{{
                t('core.queue.triggers.reset')
              }}</a-button>
            </div>
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>
  </a-card>
</template>

<style scoped>
.queue-cycle-settings :deep(.ant-form-item-label > label) {
  font-weight: 600;
}

.queue-cycle-settings {
  margin-bottom: 24px;
}
.queue-cycle-settings :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}
.queue-cycle-settings :deep(.ant-form-item) {
  margin-bottom: 0;
}
.cycle-next-run {
  display: flex;
  align-items: center;
  height: 40px;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
}
.cycle-next-run-time {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  padding: 0 11px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  font-size: 14px;
  white-space: nowrap;
}
.cycle-next-run > .ant-btn {
  flex-shrink: 0;
  height: 100%;
  padding-inline: 10px;
  border: 0;
  border-left: 1px solid var(--ant-color-border);
  border-radius: 0;
  box-shadow: none;
  font-size: 14px;
}
@media (max-width: 575px) {
  .queue-cycle-settings :deep(.ant-form-item) {
    margin-bottom: 16px;
  }
}
</style>
