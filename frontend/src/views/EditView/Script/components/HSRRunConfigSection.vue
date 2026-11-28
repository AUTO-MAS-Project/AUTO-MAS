<script setup lang="ts">
import { ThunderboltOutlined } from '@ant-design/icons-vue'
import { SectionCard, SwitchTile } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import type { HSRConfig_Run } from '@/api'
import ScriptRunLimitField from './ScriptRunLimitField.vue'

defineProps<{ showLowPerformance: boolean }>()
const run = defineModel<HSRConfig_Run>('run', { required: true })
const emit = defineEmits<{
  save: [key: keyof HSRConfig_Run, value: number | string | boolean | null]
}>()
const { t } = useI18n()

function handleLowPerformanceChange(value: boolean) {
  run.value.LowPerformanceMode = value
  emit('save', 'LowPerformanceMode', value)
}
</script>

<template>
  <SectionCard variant="card" :title="t('core.edit.runConfiguration')" :icon="ThunderboltOutlined">
    <a-row :gutter="24">
      <a-col :xs="24" :md="12">
        <ScriptRunLimitField
          v-model="run.ProxyTimesLimit"
          kind="daily"
          enhanced
          :label="t('core.edit.runsPerDayThis')"
          :hint="t('core.edit.k0MeansNoLimit')"
          @change="emit('save', 'ProxyTimesLimit', $event)"
        />
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item :label="t('core.edit.maximumAttemptsFailedTask')">
          <a-input-number
            v-model:value="run.RunTimesLimit"
            :min="1"
            :max="9999"
            style="width: 100%"
            @change="emit('save', 'RunTimesLimit', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item :label="t('core.edit.dailyTaskTimeoutMinutes')">
          <a-input-number
            v-model:value="run.DailyTimeLimit"
            :min="1"
            :max="9999"
            style="width: 100%"
            @change="emit('save', 'DailyTimeLimit', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item :label="t('core.edit.weeklyTaskTimeoutMinutes')">
          <a-input-number
            v-model:value="run.WeeklyTimeLimit"
            :min="1"
            :max="9999"
            style="width: 100%"
            @change="emit('save', 'WeeklyTimeLimit', $event)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <!-- 低性能兼容只作用于三月七，没填三月七路径时不渲染 -->
    <a-row v-if="showLowPerformance" :gutter="24" style="margin-bottom: 12px">
      <a-col :xs="24" :md="12">
        <SwitchTile
          :checked="Boolean(run.LowPerformanceMode)"
          :title="t('core.edit.enableLowPerformanceCompatibility')"
          :description="t('core.edit.appliesMarch7thDivergentUniverse')"
          @change="handleLowPerformanceChange"
        />
      </a-col>
    </a-row>
  </SectionCard>
</template>
