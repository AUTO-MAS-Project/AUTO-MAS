<template>
  <a-flex class="section-header" justify="space-between" align="center" wrap="wrap" gap="small">
    <h3>{{ t('core.edit.taskConfiguration') }}</h3>
    <a-space>
      <a-button size="small" @click="emit('restore')">
        <template #icon><HistoryOutlined /></template>
        {{ t('core.edit.configRestoreTitle') }}
      </a-button>
    </a-space>
  </a-flex>

  <a-card class="config-card">
    <a-form layout="vertical">
      <UniversalPlanSelector
        :script-id="scriptId"
        :user-id="userId"
        :plan-mode="form.Info.PlanMode"
        :plan-type="PLAN_CONFIG_TYPES.OKWW"
        :disabled="disabled"
        @change="form.Info.PlanMode = $event"
      />
    </a-form>
  </a-card>
  <OkwwTaskConfigSection
    v-model="form.Task"
    :quick-config="
      form.Info.IfQuickConfig && (!form.Info.PlanMode || form.Info.PlanMode === 'Fixed')
    "
    :script-id="scriptId"
    :save-task="saveTask"
    :disabled="disabled"
    @save="emit('save')"
  />
</template>
<script setup lang="ts">
import { HistoryOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import UniversalPlanSelector from '../UniversalPlanSelector.vue'
import OkwwTaskConfigSection from './OkwwTaskConfigSection.vue'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
type Task = InstanceType<typeof OkwwTaskConfigSection>['$props']['modelValue']
const form = defineModel<{
  Info: { PlanMode?: string | null; IfQuickConfig: boolean }
  Task: Task
}>({ required: true })
defineProps<{
  scriptId: string
  userId: string
  disabled: boolean
  saveTask: () => Promise<boolean>
}>()
const { t } = useI18n()
const emit = defineEmits<{ save: []; restore: [] }>()
</script>
