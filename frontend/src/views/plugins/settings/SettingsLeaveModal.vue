<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { AppModal } from '@/components/ui'

/** 离开设置页时有未保存更改的确认：继续编辑、放弃并离开、保存并离开。 */
defineProps<{ open: boolean; count: number; saving: boolean; saveDisabled?: boolean }>()
const emit = defineEmits<{ stay: []; discard: []; save: [] }>()
const { t } = useI18n()
</script>

<template>
  <AppModal
    :open="open"
    :width="416"
    :title="t('core.edit.youHaveUnsavedChanges')"
    :submitting="saving"
    footer="custom"
    @cancel="emit('stay')"
  >
    <p class="settings-leave-text">{{ t('core.plugins.unsavedCount', { count }) }}</p>
    <template #footer>
      <a-button :disabled="saving" @click="emit('stay')">{{ t('core.edit.keepEditing') }}</a-button>
      <a-button danger :disabled="saving" @click="emit('discard')">{{
        t('core.plugins.discardAndLeave')
      }}</a-button>
      <a-button type="primary" :loading="saving" :disabled="saveDisabled" @click="emit('save')">{{
        t('core.plugins.saveAndLeave')
      }}</a-button>
    </template>
  </AppModal>
</template>

<style scoped>
.settings-leave-text {
  margin: 0;
  color: var(--ant-color-text-secondary);
}
</style>
