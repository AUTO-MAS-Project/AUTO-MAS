<script setup lang="ts">
import { useI18n } from 'vue-i18n'

/** 设置页底部的未保存提示栏：几项未保存、放弃、保存。 */
defineProps<{ count: number; saving: boolean; disabled: boolean }>()
const emit = defineEmits<{ discard: []; save: [] }>()
const { t } = useI18n()
</script>

<template>
  <div class="settings-dirty-bar" role="status">
    <span class="settings-dirty-text">{{ t('core.plugins.unsavedCount', { count }) }}</span>
    <a-button :disabled="saving || disabled" @click="emit('discard')">{{
      t('core.plugins.discardChanges')
    }}</a-button>
    <a-button type="primary" :loading="saving" :disabled="disabled" @click="emit('save')">{{
      t('core.plugins.save')
    }}</a-button>
  </div>
</template>

<style scoped>
.settings-dirty-bar {
  position: sticky;
  bottom: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-primary);
  border-radius: 8px;
  background: var(--ant-color-bg-elevated);
  box-shadow: var(--ant-box-shadow-secondary);
}

.settings-dirty-text {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
