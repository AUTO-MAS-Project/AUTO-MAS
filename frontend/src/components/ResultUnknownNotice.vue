<template>
  <a-alert
    type="warning"
    show-icon
    :message="t('resultUnknown.title')"
    class="result-unknown-notice"
  >
    <template #description>
      <div>{{ description }}</div>
      <div v-if="taskId" class="result-unknown-task">
        {{ t('resultUnknown.taskId') }}: {{ taskId }}
      </div>
    </template>
    <template #action>
      <a-button type="link" size="small" @click="emit('query')">
        {{ t('resultUnknown.query') }}
      </a-button>
    </template>
  </a-alert>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

defineOptions({ name: 'ResultUnknownNotice' })

const props = defineProps<{
  taskId?: string
  messageKey?: string
}>()

const emit = defineEmits<{ query: [] }>()

const { t } = useI18n()

const description = computed(() =>
  props.messageKey ? t(props.messageKey) : t('resultUnknown.description')
)
</script>

<style scoped>
.result-unknown-notice {
  margin-bottom: 8px;
}

.result-unknown-task {
  margin-top: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
</style>
