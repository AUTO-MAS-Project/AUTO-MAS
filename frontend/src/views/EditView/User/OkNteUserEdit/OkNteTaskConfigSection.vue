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
            <a-input
              :value="startupArguments"
              :placeholder="previewError"
              :title="previewError"
              size="large"
              readonly
            />
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>
  </a-card>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { OkNteSetupService } from '@/composables/useAdapterSetupApi'

const taskIndex = defineModel<number>('taskIndex', { required: true })
const props = defineProps<{
  options: { value: number; label: string }[]
  scriptId: string
  exitOnFinish: boolean
  disabled: boolean
  loading: boolean
}>()
const emit = defineEmits<{ change: [value: number] }>()
const { t } = useI18n()
const effectiveTaskIndex = computed(() => (props.disabled ? 2 : taskIndex.value))
const argument = ref('')
const previewError = ref('')
const startupArguments = computed(() =>
  argument.value ? `-t ${argument.value}${props.exitOnFinish ? ' -e' : ''}` : ''
)

watch(
  [() => props.scriptId, effectiveTaskIndex, () => props.loading],
  async ([scriptId, index, loading], _, onCleanup) => {
    argument.value = ''
    previewError.value = ''
    if (loading) return

    const request = OkNteSetupService.getOknteTaskArgumentApiScriptsOknteTaskArgumentGet(
      scriptId,
      index
    )
    let stale = false
    onCleanup(() => {
      stale = true
      request.cancel()
    })
    try {
      const response = await request
      if (stale) return
      if (response.code === 200 && response.data) argument.value = response.data
      else previewError.value = response.message || t('core.edit.launchArgumentPreviewUnavailable')
    } catch {
      if (!stale) previewError.value = t('core.edit.launchArgumentPreviewUnavailable')
    }
  },
  { immediate: true }
)
</script>
