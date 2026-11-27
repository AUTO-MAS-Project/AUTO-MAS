<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { UploadSubmissionMode } from '../uploadPrecheck'

defineProps<{
  mode: UploadSubmissionMode
  rememberPreference: boolean
  disabled: boolean
}>()

defineEmits<{
  'update:mode': [value: UploadSubmissionMode]
  'update:rememberPreference': [value: boolean]
}>()

const { t } = useI18n()
</script>

<template>
  <section class="mode-section">
    <div class="mode-head">
      <span class="mode-label">{{ t('core.themeStore.upload.mode.title') }}</span>
      <a-checkbox
        :checked="rememberPreference"
        :disabled="disabled"
        @update:checked="$emit('update:rememberPreference', Boolean($event))"
      >
        <span class="mode-remember">{{ t('core.themeStore.upload.mode.remember') }}</span>
      </a-checkbox>
    </div>

    <div class="mode-cards" role="radiogroup" :aria-label="t('core.themeStore.upload.mode.title')">
      <button
        type="button"
        role="radio"
        :aria-checked="mode === 'preview'"
        :disabled="disabled"
        class="mode-card"
        :class="{ 'is-selected': mode === 'preview' }"
        @click="$emit('update:mode', 'preview')"
      >
        <div class="mode-card-top">
          <span class="mode-radio-dot" aria-hidden="true" />
          <span class="mode-card-title">{{ t('core.themeStore.upload.mode.previewTitle') }}</span>
          <a-tag color="blue" class="mode-card-tag">
            {{ t('core.themeStore.upload.mode.recommended') }}
          </a-tag>
        </div>
        <span class="mode-card-desc">{{ t('core.themeStore.upload.mode.previewDesc') }}</span>
      </button>

      <button
        type="button"
        role="radio"
        :aria-checked="mode === 'direct'"
        :disabled="disabled"
        class="mode-card"
        :class="{ 'is-selected': mode === 'direct' }"
        @click="$emit('update:mode', 'direct')"
      >
        <div class="mode-card-top">
          <span class="mode-radio-dot" aria-hidden="true" />
          <span class="mode-card-title">{{ t('core.themeStore.upload.mode.directTitle') }}</span>
          <a-tag class="mode-card-tag">{{ t('core.themeStore.upload.mode.fastBadge') }}</a-tag>
        </div>
        <span class="mode-card-desc">{{ t('core.themeStore.upload.mode.directDesc') }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.mode-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mode-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.mode-label {
  color: var(--ant-color-text);
  font-weight: 600;
}

.mode-remember {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.mode-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.mode-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1.5px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease;
}

.mode-card:hover:not(:disabled) {
  border-color: var(--ant-color-primary-border);
}

.mode-card.is-selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.mode-card:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.mode-card-top {
  display: flex;
  gap: 6px;
  align-items: center;
}

.mode-radio-dot {
  position: relative;
  width: 14px;
  height: 14px;
  flex: none;
  border: 1.5px solid var(--ant-color-border);
  border-radius: 50%;
}

.mode-card.is-selected .mode-radio-dot {
  border-color: var(--ant-color-primary);
}

.mode-card.is-selected .mode-radio-dot::after {
  content: '';
  position: absolute;
  inset: 2px;
  border-radius: 50%;
  background: var(--ant-color-primary);
}

.mode-card-title {
  font-size: 13px;
  font-weight: 600;
}

.mode-card-tag {
  margin-inline-start: auto;
  margin-inline-end: 0;
}

.mode-card-desc {
  padding-left: 20px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 18px;
}

@media (max-width: 600px) {
  .mode-cards {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
