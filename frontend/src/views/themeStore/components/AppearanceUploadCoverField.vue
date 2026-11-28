<script setup lang="ts">
import { PictureOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { AppearanceCoverMode } from '@/composables/useShareApi'

defineProps<{
  updating: boolean
  disabled: boolean
  coverImage: string | null
  coverAlt: string
  coverMode: AppearanceCoverMode
  coverModes: AppearanceCoverMode[]
  coverPath: string | null
  hasPackagePreview: boolean
}>()

defineEmits<{
  'update:coverMode': [mode: AppearanceCoverMode]
  'pick-cover': []
  'use-package-cover': []
}>()

const COVER_MODE_LABELS: Record<AppearanceCoverMode, string> = {
  inherit: 'core.themeStore.upload.coverInherit',
  package: 'core.themeStore.upload.coverPackage',
  custom: 'core.themeStore.upload.coverCustom',
}

const { t } = useI18n()
const fileName = (value: string): string => value.split(/[\\/]/).pop() ?? value
</script>

<template>
  <section class="upload-section">
    <div class="upload-label">{{ t('core.themeStore.upload.cover') }}</div>
    <div class="upload-cover">
      <div class="upload-cover-frame">
        <img v-if="coverImage" :src="coverImage" :alt="coverAlt" class="upload-cover-image" />
        <PictureOutlined v-else class="upload-cover-placeholder" />
      </div>
      <div class="upload-cover-actions">
        <a-radio-group
          v-if="updating"
          :value="coverMode"
          :disabled="disabled"
          class="upload-cover-modes"
          @update:value="$emit('update:coverMode', $event)"
        >
          <a-radio v-for="mode in coverModes" :key="mode" :value="mode">
            {{ t(COVER_MODE_LABELS[mode]) }}
          </a-radio>
        </a-radio-group>
        <span v-if="coverMode === 'custom' && coverPath" class="upload-file-name">
          {{ fileName(coverPath) }}
        </span>
        <template v-else-if="!updating">
          <span v-if="coverMode === 'package'" class="upload-hint">
            {{ t('core.themeStore.upload.coverFromPackage') }}
          </span>
          <span v-else class="upload-hint upload-hint-warning">
            {{ t('core.themeStore.upload.coverRequired') }}
          </span>
        </template>
        <span v-if="!updating || coverMode === 'custom'" class="upload-cover-buttons">
          <a-button size="small" :disabled="disabled" @click="$emit('pick-cover')">
            {{ t('core.themeStore.upload.pickCover') }}
          </a-button>
          <a-button
            v-if="!updating && coverMode === 'custom' && hasPackagePreview"
            size="small"
            type="link"
            :disabled="disabled"
            @click="$emit('use-package-cover')"
          >
            {{ t('core.themeStore.upload.usePackageCover') }}
          </a-button>
        </span>
        <span v-if="!updating || coverMode === 'custom'" class="upload-hint">
          {{ t('core.themeStore.upload.coverSpec') }}
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.upload-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.upload-label {
  color: var(--ant-color-text);
  font-weight: 600;
}

.upload-file-name {
  min-width: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.upload-cover {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.upload-cover-frame {
  display: flex;
  width: 192px;
  flex: none;
  aspect-ratio: 16 / 10;
  overflow: hidden;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-layout);
}

.upload-cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.upload-cover-placeholder {
  color: var(--ant-color-text-quaternary);
  font-size: 28px;
}

.upload-cover-actions {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.upload-cover-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.upload-hint {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.upload-hint-warning {
  color: var(--ant-color-warning-text);
}

.upload-cover-modes {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
