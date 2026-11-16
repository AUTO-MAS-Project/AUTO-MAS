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

  <OkwwTaskConfigSection
    v-model="form.Task"
    :overlay-enabled="form.Info.IfQuickConfig"
    :script-id="scriptId"
    :user-id="userId"
    :save-task="saveTask"
    :disabled="disabled"
    @save="emit('save')"
    @refresh="emit('refresh')"
    @busy="emit('busy', $event)"
  />
</template>
<script setup lang="ts">
import { HistoryOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import OkwwTaskConfigSection from './OkwwTaskConfigSection.vue'
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
const emit = defineEmits<{ save: []; restore: []; refresh: []; busy: [value: boolean] }>()
</script>
