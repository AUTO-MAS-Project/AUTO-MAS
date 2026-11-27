<script setup lang="ts">
import { computed } from 'vue'
import { EyeOutlined, SkinOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { OnlineAppearancePreview } from '@/types/appearance'
import type { AppearanceCategory } from '@/types/mascotPack'
import { formatAppearanceFileSize } from '../useOnlineAppearance'
import type { UploadPrecheckResult } from '../uploadPrecheck'
import UploadPrecheckPanel from './UploadPrecheckPanel.vue'

const props = defineProps<{
  categoryKey: AppearanceCategory
  displayName: string
  description: string
  changeNote: string
  authorName: string
  updating: boolean
  coverImage: string | null
  fileSize: number
  appearance: OnlineAppearancePreview
  precheck: UploadPrecheckResult
}>()

defineEmits<{
  'try-on-window': []
}>()

const { t } = useI18n()

const swatches = computed(() => {
  const tokens = props.appearance.tokens ?? props.appearance.tryOnAppearance?.tokens
  if (!tokens) return []
  return [
    tokens.colorPrimary,
    tokens.colorBgLayout,
    tokens.colorBgContainer,
    tokens.colorBorder,
    tokens.colorText,
  ].filter((color): color is string => Boolean(color))
})

const resolvedMode = computed(() => props.appearance.mode ?? props.appearance.tryOnAppearance?.mode)
</script>

<template>
  <div class="preview-step">
    <div class="preview-col">
      <div class="preview-section-head">
        <span class="preview-section-title">{{
          t('core.themeStore.upload.preview.storeCard')
        }}</span>
        <a-tag color="blue" class="preview-tag">
          {{
            updating
              ? t('core.themeStore.upload.targetUpdate')
              : t('core.themeStore.upload.targetNew')
          }}
        </a-tag>
      </div>

      <div class="preview-card-showcase">
        <div class="mock-store-card">
          <div class="mock-cover">
            <img v-if="coverImage" :src="coverImage" :alt="displayName" class="mock-cover-image" />
            <SkinOutlined v-else class="mock-cover-placeholder" />
            <span class="mock-cat-chip">{{ t(`core.themeStore.categories.${categoryKey}`) }}</span>
          </div>
          <div class="mock-body">
            <div class="mock-title">{{ displayName || appearance.name }}</div>
            <div class="mock-meta">
              <span>@{{ authorName || t('core.themeStore.unknownAuthor') }}</span>
              <span>{{ formatAppearanceFileSize(fileSize) }}</span>
            </div>
          </div>
        </div>

        <div class="preview-summary">
          <div class="preview-summary-name">{{ displayName || appearance.name }}</div>
          <p class="preview-summary-desc">
            {{ description || t('core.themeStore.noDescription') }}
          </p>
          <div v-if="changeNote" class="preview-change-note">
            <strong>{{ t('core.themeStore.upload.changeNote') }}：</strong>{{ changeNote }}
          </div>
        </div>
      </div>

      <div v-if="swatches.length > 0 || appearance.tryOnAppearance" class="preview-swatches-box">
        <div class="preview-section-head">
          <span class="preview-section-title">{{
            t('core.themeStore.upload.preview.palette')
          }}</span>
          <a-button
            v-if="appearance.tryOnAppearance"
            size="small"
            type="primary"
            ghost
            @click="$emit('try-on-window')"
          >
            <template #icon><EyeOutlined /></template>
            {{ t('core.themeStore.upload.preview.tryOnWindow') }}
          </a-button>
        </div>
        <div v-if="swatches.length > 0 || resolvedMode" class="preview-swatches-row">
          <div v-if="swatches.length > 0" class="swatch-list">
            <span
              v-for="(color, index) in swatches"
              :key="`${index}-${color}`"
              class="swatch-chip"
              :style="{ background: color }"
              :title="color"
            />
          </div>
          <span v-if="resolvedMode" class="preview-mode-text">
            {{
              resolvedMode === 'dark'
                ? t('core.setting.themeMode.dark')
                : t('core.setting.themeMode.light')
            }}
          </span>
        </div>
      </div>
    </div>

    <div class="preview-col">
      <UploadPrecheckPanel :result="precheck" />
      <a-alert
        v-if="appearance.hasBundledMascot"
        type="info"
        show-icon
        :message="t('core.themeStore.tryOn.drawerMascotNote')"
      />
    </div>
  </div>
</template>

<style scoped>
.preview-step {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 16px;
}

.preview-col {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
}

.preview-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.preview-section-title {
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
}

.preview-tag {
  margin-inline-end: 0;
}

.preview-card-showcase {
  display: grid;
  grid-template-columns: 204px minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-fill-tertiary);
}

.mock-store-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.mock-cover {
  position: relative;
  display: flex;
  aspect-ratio: 16 / 10;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-bg-layout);
}

.mock-cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.mock-cover-placeholder {
  color: var(--ant-color-text-quaternary);
  font-size: 24px;
}

.mock-cat-chip {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--ant-color-bg-mask);
  color: var(--ant-color-text-light-solid);
  font-size: 11px;
}

.mock-body {
  padding: 8px 10px;
}

.mock-title {
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mock-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 2px;
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
}

.preview-summary {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.preview-summary-name {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.preview-summary-desc {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 18px;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.preview-change-note {
  padding: 6px 8px;
  border: 1px solid var(--ant-color-primary-border);
  border-radius: 6px;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-text);
  font-size: 12px;
}

.preview-swatches-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-fill-tertiary);
}

.preview-swatches-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.swatch-list {
  display: flex;
  gap: 8px;
}

.swatch-chip {
  width: 22px;
  height: 22px;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
}

.preview-mode-text {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

@media (max-width: 720px) {
  .preview-step,
  .preview-card-showcase {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
