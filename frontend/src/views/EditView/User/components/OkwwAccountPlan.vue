<template>
  <SectionCard variant="plain" :title="t('core.edit.taskConfiguration')">
    <template #actions>
      <a-button size="small" @click="emit('restore')">
        <template #icon><HistoryOutlined /></template>
        {{ t('core.edit.configRestoreTitle') }}
      </a-button>
    </template>

    <OkwwTaskConfigSection
      v-model="form.Task"
      :overlay-enabled="form.Info.IfQuickConfig"
      :context-key="`${form.Info.Base}|${form.Info.PlanMode}`"
      :script-id="scriptId"
      :user-id="userId"
      :save-task="saveTask"
      :disabled="disabled"
      @save="emit('save')"
      @refresh="emit('refresh')"
      @busy="emit('busy', $event)"
    />
  </SectionCard>
</template>
<script setup lang="ts">
import { HistoryOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { SectionCard } from '@/components/ui'
import OkwwTaskConfigSection from './OkwwTaskConfigSection.vue'
type Task = InstanceType<typeof OkwwTaskConfigSection>['$props']['modelValue']
const form = defineModel<{
  Info: { Base?: string; PlanMode?: string | null; IfQuickConfig: boolean }
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
