<template>
  <div class="section-header">
    <h3>{{ t('core.edit.taskConfiguration') }}</h3>
  </div>
  <a-card class="config-card" :loading="loading">
    <a-form layout="vertical" class="config-form">
      <a-row :gutter="24">
        <a-col :span="12">
          <a-form-item>
            <template #label>
              <FieldLabelWithHint
                :text="t('core.edit.startTaskTN')"
                :hint="t('core.edit.taskNumbersMatchOk')"
                variant="form"
              />
            </template>
            <a-select
              v-model:value="taskIndex"
              :disabled="disabled"
              size="large"
              @change="(value: number) => emit('change', value)"
            >
              <a-select-option v-for="item in options" :key="item.value" :value="item.value">
                {{ item.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item>
            <template #label>
              <FieldLabelWithHint
                :text="t('core.edit.currentLaunchArguments')"
                :hint="t('core.edit.argumentsGeneratedFromTask')"
                variant="form"
              />
            </template>
            <a-input :value="startupArguments" size="large" readonly />
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>
  </a-card>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
const taskIndex = defineModel<number>('taskIndex', { required: true })
defineProps<{
  options: { value: number; label: string }[]
  startupArguments: string
  disabled: boolean
  loading: boolean
}>()
const emit = defineEmits<{ change: [value: number] }>()
const { t } = useI18n()
</script>
