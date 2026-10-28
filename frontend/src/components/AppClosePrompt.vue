<template>
  <a-modal
    v-model:open="modalOpen"
    :footer="null"
    :closable="!busy"
    :mask-closable="false"
    :keyboard="!busy"
    :width="480"
    centered
    wrap-class-name="app-close-prompt-modal"
    @cancel="emit('cancel')"
  >
    <template #title>
      <div class="close-prompt-title">
        <span class="close-prompt-title-icon" aria-hidden="true">
          <PoweroffOutlined />
        </span>
        <span>{{ t('bootstrap.comp.confirmCloseApp') }}</span>
      </div>
    </template>

    <div class="close-prompt">
      <div class="close-prompt-actions">
        <a-button class="close-choice close-choice--quit" :disabled="busy" @click="choose('quit')">
          <span class="close-choice-icon" aria-hidden="true">
            <PoweroffOutlined />
          </span>
          <span class="close-choice-label">
            {{ t('bootstrap.comp.closeMas') }}
          </span>
          <ArrowRightOutlined class="close-choice-arrow" aria-hidden="true" />
        </a-button>
        <a-button class="close-choice close-choice--tray" :disabled="busy" @click="choose('tray')">
          <span class="close-choice-icon" aria-hidden="true">
            <PushpinOutlined />
          </span>
          <span class="close-choice-label">
            {{ t('bootstrap.comp.minimizeMasToTray') }}
          </span>
          <ArrowRightOutlined class="close-choice-arrow" aria-hidden="true" />
        </a-button>
      </div>
      <div class="close-prompt-footer">
        <a-checkbox v-model:checked="rememberChoice" :disabled="busy">
          {{ t('bootstrap.comp.dontAskAgain') }}
        </a-checkbox>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowRightOutlined, PoweroffOutlined, PushpinOutlined } from '@ant-design/icons-vue'
import type { AppCloseAction } from '@/utils/appClosePreferences'

const props = defineProps<{ open: boolean; busy: boolean }>()
const emit = defineEmits<{
  'update:open': [open: boolean]
  choose: [action: AppCloseAction, remember: boolean]
  cancel: []
}>()

const { t } = useI18n()
const rememberChoice = ref(false)
const modalOpen = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})

watch(
  () => props.open,
  open => {
    if (open) rememberChoice.value = false
  }
)

const choose = (action: AppCloseAction): void => {
  emit('choose', action, rememberChoice.value)
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
  padding: 16px 20px 14px;
  border-bottom: 0;
  background: transparent;
}

:global(.app-close-prompt-modal .ant-modal-body) {
  padding: 0 20px 18px;
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
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
  padding-inline-end: 32px;
  color: var(--ant-color-text-heading);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.35;
}

.close-prompt-title-icon,
.close-choice-icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
}

.close-prompt-title-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  font-size: 15px;
}

.close-prompt {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.close-prompt-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.close-choice {
  display: grid !important;
  min-width: 0;
  min-height: 56px;
  height: auto;
  grid-template-columns: 32px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  border-color: var(--ant-color-border);
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  box-shadow: none;
  text-align: start;
  white-space: normal;
}

.close-choice-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  font-size: 16px;
}

.close-choice-label {
  min-width: 0;
  color: inherit;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.35;
}

.close-choice-arrow {
  color: currentColor;
  font-size: 12px;
  opacity: 0.7;
  transition: transform 0.18s ease;
}

.close-choice:hover .close-choice-arrow {
  transform: translateX(2px);
}

.close-choice--quit {
  border-color: var(--ant-color-border);
}

.close-choice--quit .close-choice-icon {
  color: var(--ant-color-error);
  background: var(--ant-color-fill-tertiary);
}

.close-choice--quit:hover,
.close-choice--quit:focus-visible {
  color: var(--ant-color-text) !important;
  border-color: var(--ant-color-error-border) !important;
  background: var(--ant-color-error-bg) !important;
}

.close-choice--tray {
  border-color: var(--ant-color-border);
}

.close-choice--tray .close-choice-icon {
  color: var(--ant-color-primary);
  background: var(--ant-color-fill-tertiary);
}

.close-choice--tray:hover,
.close-choice--tray:focus-visible {
  color: var(--ant-color-text) !important;
  border-color: var(--ant-color-primary-border) !important;
  background: var(--ant-color-primary-bg-hover) !important;
}

.close-prompt-footer {
  display: flex;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.close-prompt-footer :deep(.ant-checkbox-wrapper) {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

@media (max-width: 520px) {
  :global(.app-close-prompt-modal .ant-modal-header) {
    padding-inline: 16px;
  }

  :global(.app-close-prompt-modal .ant-modal-body) {
    padding-inline: 16px;
  }

  .close-prompt-actions {
    grid-template-columns: 1fr;
  }
}
</style>
