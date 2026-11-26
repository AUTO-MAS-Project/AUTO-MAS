<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PreparedOnlineAppearance } from '../useOnlineAppearance'

const props = defineProps<{
  displayName: string
  detailCover?: string
  prepared: PreparedOnlineAppearance | null
  preparing: boolean
  prepareError: string | null
  hasVersions: boolean
}>()

defineEmits<{
  prepare: []
}>()

const { t } = useI18n()

const previewImage = computed(
  () => props.prepared?.appearance.previewUrl ?? props.detailCover ?? undefined
)

const swatchStyle = computed(() => {
  const tokens = props.prepared?.appearance.tokens
  const dark = props.prepared?.appearance.mode === 'dark'
  return {
    '--swatch-layout': tokens?.colorBgLayout ?? (dark ? '#000000' : '#f5f5f5'),
    '--swatch-container': tokens?.colorBgContainer ?? (dark ? '#141414' : '#ffffff'),
    '--swatch-text': tokens?.colorText ?? (dark ? '#ffffffd9' : '#000000e0'),
    '--swatch-text-secondary': tokens?.colorTextSecondary ?? (dark ? '#ffffff73' : '#00000073'),
    '--swatch-border': tokens?.colorBorder ?? (dark ? '#424242' : '#d9d9d9'),
    '--swatch-primary': tokens?.colorPrimary ?? '#1677ff',
    '--swatch-radius': `${tokens?.borderRadius ?? 6}px`,
  }
})
</script>

<template>
  <section class="drawer-preview">
    <div v-if="preparing" class="drawer-preview-state">
      <img
        v-if="detailCover"
        :src="detailCover"
        :alt="displayName"
        class="drawer-preview-image drawer-preview-dim"
      />
      <a-spin :tip="t('core.themeStore.preparing')" class="drawer-preview-spin" />
    </div>
    <div v-else-if="prepareError" class="drawer-preview-state">
      <a-result status="warning" :sub-title="prepareError">
        <template #extra>
          <a-button @click="$emit('prepare')">{{ t('core.themeStore.retry') }}</a-button>
        </template>
      </a-result>
    </div>
    <template v-else-if="previewImage || prepared">
      <img
        v-if="previewImage"
        :src="previewImage"
        :alt="displayName"
        class="drawer-preview-image"
      />
      <div v-else class="drawer-swatch" :style="swatchStyle">
        <span class="swatch-sider" />
        <span class="swatch-card">
          <span class="swatch-line strong" />
          <span class="swatch-line" />
          <span class="swatch-button" />
        </span>
      </div>
    </template>
    <div v-else-if="!hasVersions" class="drawer-preview-state">
      <NoData :description="t('core.themeStore.noVersions')" />
    </div>
    <div v-else class="drawer-preview-state">
      <a-button @click="$emit('prepare')">{{ t('core.themeStore.downloadPreview') }}</a-button>
    </div>
  </section>
</template>

<style scoped>
.drawer-preview {
  display: flex;
  aspect-ratio: 16 / 10;
  overflow: hidden;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-bg-layout);
}

.drawer-preview-state {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.drawer-preview-dim {
  position: absolute;
  inset: 0;
  opacity: 0.45;
}

.drawer-preview-spin {
  position: relative;
}

.drawer-preview-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.drawer-swatch {
  display: flex;
  width: 100%;
  height: 100%;
  gap: 12px;
  padding: 16px;
  background: var(--swatch-layout);
}

.swatch-sider {
  width: 22%;
  border-radius: var(--swatch-radius);
  background: var(--swatch-primary);
  opacity: 0.24;
}

.swatch-card {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--swatch-border);
  border-radius: var(--swatch-radius);
  background: var(--swatch-container);
}

.swatch-line {
  width: 70%;
  height: 8px;
  border-radius: 4px;
  background: var(--swatch-text-secondary);
}

.swatch-line.strong {
  width: 45%;
  height: 10px;
  background: var(--swatch-text);
}

.swatch-button {
  width: 38%;
  height: 20px;
  margin-top: auto;
  border-radius: var(--swatch-radius);
  background: var(--swatch-primary);
}
</style>
