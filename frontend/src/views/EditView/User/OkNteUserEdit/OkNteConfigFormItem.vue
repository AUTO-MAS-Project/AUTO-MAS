<template>
  <a-form-item>
    <template #label>
      <span>{{ field.label || field.name }}</span>
      <a-tooltip v-if="field.description" :title="field.description">
        <QuestionCircleOutlined
          tabindex="0"
          :aria-label="t('core.plan.oknte.fieldHelp', { field: field.label || field.name })"
          class="field-help"
        />
      </a-tooltip>
    </template>
    <slot />
  </a-form-item>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
const { t } = useI18n()
defineProps<{ field: { name: string; label?: string; description?: string } }>()
</script>
<style scoped>
.field-help {
  margin-left: 6px;
  color: var(--ant-color-text-tertiary);
  cursor: help;
}
</style>
