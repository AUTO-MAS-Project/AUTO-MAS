<template>
  <div class="user-basic-info-fields">
    <a-row :gutter="24">
      <a-col :xs="24" :md="8">
        <a-form-item :name="namePath" :label="t('core.edit.username')" required>
          <a-input
            size="middle"
            v-model:value="userName"
            :placeholder="t('core.edit.enterUsername')"
            :disabled="disabled"
            @blur="emit('save-name')"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item :label="t('core.edit.enabled')">
          <a-select
            size="middle"
            :value="status ? 'on' : 'off'"
            :disabled="disabled"
            :options="statusOptions"
            @change="changeStatus"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item>
          <template #label
            ><FieldLabelWithHint
              :text="t('core.edit.daysLeft')"
              :hint="t('core.edit.daysLeftAccount1')"
              variant="form"
          /></template>
          <a-input-number
            size="middle"
            v-model:value="remainedDay"
            :min="-1"
            :max="9999"
            :disabled="disabled"
            style="width: 100%"
            @blur="emit('save-days')"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-form-item :label="t('core.edit.note')">
      <a-textarea
        size="middle"
        v-model:value="notes"
        :placeholder="t('core.edit.enterNote')"
        :auto-size="{ minRows: 2, maxRows: 4 }"
        :disabled="disabled"
        @blur="emit('save-notes')"
      />
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

withDefaults(defineProps<{ disabled?: boolean; namePath?: string | string[] }>(), {
  disabled: false,
  namePath: 'userName',
})
const userName = defineModel<string>('userName', { required: true })
const status = defineModel<boolean>('status', { required: true })
const remainedDay = defineModel<number>('remainedDay', { required: true })
const notes = defineModel<string>('notes', { required: true })
const emit = defineEmits<{
  'save-name': []
  'save-status': []
  'save-days': []
  'save-notes': []
}>()
const { t } = useI18n()
const statusOptions = computed(() => [
  { label: t('core.edit.enabled3'), value: 'on' },
  { label: t('core.edit.disabled'), value: 'off' },
])
function changeStatus(value: string) {
  status.value = value === 'on'
  emit('save-status')
}
</script>

<style scoped>
.user-basic-info-fields :deep(.ant-form-item) {
  margin-bottom: 16px;
}

.user-basic-info-fields :deep(.ant-form-item-label > label),
.user-basic-info-fields :deep(.field-label-form) {
  font-size: 14px;
  font-weight: 400;
}
</style>
