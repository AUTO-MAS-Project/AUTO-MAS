<template>
  <a-form-item
    :validate-status="previewError ? 'error' : undefined"
    :help="previewError || undefined"
  >
    <template #label>
      <a-space wrap>
        <FieldLabelWithHint
          :text="t('core.edit.okwwDailyArgumentsExample')"
          :hint="t('core.edit.okwwArgumentsExampleHint')"
          variant="form"
        />
        <a-switch
          :checked="task.IfCustomArguments"
          :loading="previewLoading || saving"
          :aria-label="t('core.edit.okwwCustomArguments')"
          @change="changeCustomArguments"
        />
        <span>{{ t('core.edit.okwwCustomArguments') }}</span>
      </a-space>
    </template>
    <template v-if="task.IfCustomArguments">
      <a-input
        v-model:value="task.CustomArguments"
        :disabled="saving || undefined"
        :placeholder="t('core.edit.okwwCustomArgumentsPlaceholder')"
        size="large"
        @blur="emit('save')"
        @press-enter="emit('save')"
      />
    </template>
    <a-input v-else :value="resolvedArguments" size="large" readonly />
  </a-form-item>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Modal } from 'ant-design-vue'
import { useOkwwArgumentsApi } from '@/composables/useOkwwArgumentsApi'
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useOkwwCustomArguments } from './useOkwwCustomArguments'
import type { OkwwTaskForm } from './okwwTaskConfig'

const task = defineModel<OkwwTaskForm>({ required: true })
const emit = defineEmits<{ save: [] }>()
const { t } = useI18n()
const props = defineProps<{ scriptId: string; save: () => Promise<boolean> }>()
const { previewArguments } = useOkwwArgumentsApi()
const resolvedArguments = ref('')
const previewError = ref('')
const previewLoading = ref(true)

const { saving, changeCustomArguments } = useOkwwCustomArguments(
  task,
  resolvedArguments,
  () => props.save(),
  onOk =>
    Modal.confirm({
      title: t('core.edit.okwwCustomArguments'),
      content: t('core.edit.okwwCustomArgumentsWarning'),
      onOk,
    })
)

onMounted(() => {
  watch(
    () => [props.scriptId, task.value.IfCustomArguments, task.value.CustomArguments] as const,
    ([scriptId, custom, argumentsText], _, onCleanup) => {
      let current = true
      resolvedArguments.value = ''
      previewError.value = ''
      previewLoading.value = true
      const timer = setTimeout(async () => {
        try {
          const response = await previewArguments(scriptId, custom, argumentsText)
          if (!current) return
          resolvedArguments.value = (response.arguments || [])
            .map(arg => (/[\s'"]/.test(arg) ? "'" + arg.replace(/'/g, "'\"'\"'") + "'" : arg))
            .join(' ')
        } catch (error) {
          if (current) previewError.value = error instanceof Error ? error.message : String(error)
        } finally {
          if (current) previewLoading.value = false
        }
      }, 200)
      onCleanup(() => {
        current = false
        clearTimeout(timer)
      })
    },
    { immediate: true }
  )
})
</script>
