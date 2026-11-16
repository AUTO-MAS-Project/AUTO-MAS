<template>
  <a-modal
    v-model:open="modalOpen"
    :footer="null"
    :closable="!busy"
    :mask-closable="false"
    :keyboard="!busy"
    :width="400"
    centered
    wrap-class-name="app-close-prompt-modal"
    @cancel="emit('cancel')"
  >
    <template #title>
      <span class="close-prompt-title">{{ t('bootstrap.comp.closeActionPrompt') }}</span>
    </template>

    <div class="close-prompt">
      <a-radio-group
        v-model:value="selectedAction"
        class="close-options"
        :disabled="busy"
        :aria-label="t('bootstrap.comp.closeActionPrompt')"
      >
        <a-radio value="tray" class="close-option">
          {{ t('bootstrap.comp.minimizeMasToTray') }}
        </a-radio>
        <a-radio value="quit" class="close-option">
          {{ t('bootstrap.comp.closeMas') }}
        </a-radio>
      </a-radio-group>

      <a-checkbox v-model:checked="rememberChoice" class="close-prompt-remember" :disabled="busy">
        {{ t('bootstrap.comp.dontAskAgain') }}
      </a-checkbox>
      <div class="close-prompt-actions">
        <a-button :disabled="busy" @click="emit('cancel')">
          {{ t('bootstrap.comp.cancel') }}
        </a-button>
        <a-button type="primary" :loading="busy" @click="confirmChoice">
          {{ t('bootstrap.comp.confirm') }}
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AppCloseAction } from '@/utils/appClosePreferences'

const props = defineProps<{
  open: boolean
  busy: boolean
  defaultAction?: AppCloseAction
}>()
const emit = defineEmits<{
  'update:open': [open: boolean]
  choose: [action: AppCloseAction, remember: boolean]
  cancel: []
}>()

const { t } = useI18n()
const rememberChoice = ref(false)
const selectedAction = ref<AppCloseAction>('tray')
const modalOpen = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})

watch(
  () => props.open,
  open => {
    if (open) {
      rememberChoice.value = false
      selectedAction.value = props.defaultAction ?? 'tray'
    }
  }
)

const confirmChoice = (): void => {
  emit('choose', selectedAction.value, rememberChoice.value)
}
</script>

<style scoped>
:global(.app-close-prompt-modal .ant-modal) {
  max-width: calc(100vw - 32px);
}

:global(.app-close-prompt-modal .ant-modal-content) {
  overflow: hidden;
  padding: 0;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--app-appearance-elevated-surface-bg, var(--ant-color-bg-elevated));
  box-shadow: var(--ant-box-shadow-secondary);
}

:global(.app-close-prompt-modal .ant-modal-header) {
  margin-bottom: 0;
  padding: 26px 28px 8px;
  border-bottom: 0;
  background: transparent;
}

:global(.app-close-prompt-modal .ant-modal-body) {
  padding: 0 32px 24px;
}

:global(.app-close-prompt-modal .ant-modal-close) {
  top: 17px;
  inset-inline-end: 17px;
  width: 30px;
  height: 30px;
  border-radius: 6px;
}

:global(.app-close-prompt-modal .ant-modal-close:hover) {
  background: var(--ant-color-fill-tertiary);
}

.close-prompt-title {
  display: block;
  padding-inline-end: 32px;
  text-align: center;
  color: var(--ant-color-text-heading);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.35;
}

.close-prompt {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.close-options {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.close-option {
  display: flex !important;
  align-items: center;
  min-height: 36px;
  margin-inline-end: 0;
  padding: 6px 8px;
  border-radius: 6px;
  color: var(--ant-color-text);
}

.close-option :deep(.ant-radio + span) {
  display: block;
  min-width: 0;
  flex: 1;
  padding-inline-start: 10px;
  font-size: 14px;
}

.close-prompt-remember {
  min-width: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  margin-top: 8px;
}

.close-prompt-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 4px;
}

.close-prompt-actions :deep(.ant-btn) {
  height: 36px;
}

@media (max-width: 520px) {
  :global(.app-close-prompt-modal .ant-modal-header) {
    padding-inline: 16px;
  }

  :global(.app-close-prompt-modal .ant-modal-body) {
    padding-inline: 20px;
  }
}
</style>
