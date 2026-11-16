<script setup lang="ts">
import QueueWeekdaysSelect from './QueueWeekdaysSelect.vue'
import SettingToggleButton from '@/components/SettingToggleButton.vue'
import { useI18n } from 'vue-i18n'
import type { Dayjs } from 'dayjs'
import QueueDeleteButton from './QueueDeleteButton.vue'

defineProps<{
  record: { enabled: boolean; days: string[]; timeValue?: Dayjs | null }
  disabled: boolean
}>()
const emit = defineEmits<{
  enabled: [value: boolean]
  days: [value: string[]]
  time: [value: Dayjs | string | null]
  remove: []
}>()
const { t } = useI18n()
</script>

<template>
  <div class="row-cell status-cell">
    <SettingToggleButton
      :model-value="record.enabled"
      :disabled="disabled"
      size="small"
      @change="value => emit('enabled', value)"
    />
  </div>
  <div class="row-cell days-cell">
    <QueueWeekdaysSelect
      :model-value="record.days"
      :disabled="disabled"
      @change="value => emit('days', value)"
    />
  </div>
  <div class="row-cell time-cell">
    <a-time-picker
      :value="record.timeValue"
      format="HH:mm"
      :placeholder="t('core.queue.time.selectTime')"
      size="small"
      :disabled="disabled"
      @change="(value: Dayjs | string | null) => emit('time', value)"
    />
  </div>
  <div class="row-cell actions-cell">
    <a-space>
      <QueueDeleteButton
        :title="t('core.queue.time.deleteConfirm')"
        :disabled="disabled"
        :confirm="() => emit('remove')"
      />
    </a-space>
  </div>
</template>

<style scoped>
.row-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  border-right: 1px solid var(--ant-color-border);
  min-width: 0;
  padding: 12px 16px;
}
.status-cell {
  padding-block: 8px;
  width: 120px;
  min-width: 120px;
  max-width: 120px;
}
.days-cell {
  flex: 4;
  min-width: 0;
}
.time-cell {
  flex: 1;
  min-width: 120px;
  max-width: 200px;
}
.actions-cell {
  width: 120px;
  padding: 12px 8px;
  flex-shrink: 0;
  border-right: none;
}

@media (max-width: 768px) {
  .row-cell {
    width: 100%;
    min-width: auto;
    max-width: none;
    border-right: none;
    border-bottom: 1px solid var(--ant-color-border);
  }
  .actions-cell {
    border-bottom: none;
  }
}
</style>
