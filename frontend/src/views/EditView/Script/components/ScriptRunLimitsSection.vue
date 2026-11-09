<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import ScriptHardTimeoutField from './ScriptHardTimeoutField.vue'
import ScriptRunLimitField from './ScriptRunLimitField.vue'

defineProps<{
  dailyHint?: string
  retryLabel?: string
  retryHint: string
  timeoutHint: string
  enhanced?: boolean
}>()

const hardTimeLimit = defineModel<number>('hardTimeLimit', { required: true })
const dailyLimit = defineModel<number>('dailyLimit', { required: true })
const retryLimit = defineModel<number>('retryLimit', { required: true })
const timeout = defineModel<number>('timeout', { required: true })
// 失焦归一化先同步到页面草稿；保存时由页面读取，避免消费尚未回刷的子组件值。
const emit = defineEmits<{
  save: [key: 'HardTimeLimit' | 'ProxyTimesLimit' | 'RunTimesLimit' | 'RunTimeLimit']
}>()
const { t } = useI18n()
</script>

<template>
  <ScriptHardTimeoutField v-model:value="hardTimeLimit" @save="emit('save', 'HardTimeLimit')" />
  <a-row :gutter="24">
    <a-col :span="8">
      <ScriptRunLimitField
        v-model="dailyLimit"
        kind="daily"
        :label="t('core.edit.runsPerDay')"
        :hint="dailyHint ?? t('core.edit.k0MeansNoLimit')"
        :enhanced="enhanced"
        @save="emit('save', 'ProxyTimesLimit')"
      />
    </a-col>
    <a-col :span="8">
      <ScriptRunLimitField
        v-model="retryLimit"
        kind="retry"
        :label="retryLabel ?? t('core.edit.retryLimit2')"
        :hint="retryHint"
        :enhanced="enhanced"
        @save="emit('save', 'RunTimesLimit')"
      />
    </a-col>
    <a-col :span="8">
      <ScriptRunLimitField
        v-model="timeout"
        kind="timeout"
        :label="t('core.edit.runTimeoutMinutes')"
        :hint="timeoutHint"
        :enhanced="enhanced"
        @save="emit('save', 'RunTimeLimit')"
      />
    </a-col>
  </a-row>
</template>
