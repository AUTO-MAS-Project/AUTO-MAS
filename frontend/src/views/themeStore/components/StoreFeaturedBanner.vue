<script setup lang="ts">
import { EyeOutlined, SkinOutlined, UpOutlined, DownOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { OnlineAppearanceItem } from '@/types/appearance'
import { formatDownloadCount } from '../storeFiltering'

defineProps<{
  item: OnlineAppearanceItem
  coverUrl?: string
  compact: boolean
  collapsed: boolean
  trying: boolean
  canTryOn: boolean
}>()

defineEmits<{
  'try-on': [item: OnlineAppearanceItem]
  'open-detail': [item: OnlineAppearanceItem]
  'toggle-collapse': []
}>()

const { t } = useI18n()
</script>

<template>
  <div v-if="collapsed" class="featured-collapsed">
    <span class="featured-collapsed-label">
      <a-tag color="blue" class="featured-tag">{{ t('core.themeStore.featured.badge') }}</a-tag>
      <span class="featured-collapsed-name">{{ item.displayName || item.fileKey }}</span>
    </span>
    <a-button size="small" type="text" @click="$emit('toggle-collapse')">
      <template #icon><DownOutlined /></template>
      {{ t('core.themeStore.featured.expand') }}
    </a-button>
  </div>

  <section v-else class="featured-banner" :class="{ 'featured-banner--compact': compact }">
    <div class="featured-media" @click="$emit('open-detail', item)">
      <img
        v-if="coverUrl"
        :src="coverUrl"
        :alt="item.displayName || item.fileKey"
        class="featured-cover"
      />
      <SkinOutlined v-else class="featured-placeholder" />
      <span class="featured-badge-wrap">
        <a-tag color="blue" class="featured-tag">{{ t('core.themeStore.featured.badge') }}</a-tag>
      </span>
    </div>

    <div class="featured-info">
      <div class="featured-head">
        <div class="featured-title-row">
          <h3 class="featured-title">{{ item.displayName || item.fileKey }}</h3>
          <a-tag v-if="item.publishedVersionNo !== null" class="featured-tag">
            v{{ item.publishedVersionNo }}
          </a-tag>
        </div>
        <a-button
          size="small"
          type="text"
          :aria-label="t('core.themeStore.featured.collapse')"
          @click="$emit('toggle-collapse')"
        >
          <template #icon><UpOutlined /></template>
        </a-button>
      </div>

      <div class="featured-meta">
        <span>@{{ item.ownerUsername || t('core.themeStore.unknownAuthor') }}</span>
        <span v-if="(item.downloadCount ?? 0) > 0">
          {{ t('core.themeStore.downloads', { count: formatDownloadCount(item.downloadCount) }) }}
        </span>
        <span v-if="item.categoryKey">
          {{ t(`core.themeStore.categories.${item.categoryKey}`) }}
        </span>
      </div>

      <p class="featured-desc">{{ item.description || t('core.themeStore.noDescription') }}</p>

      <div class="featured-actions">
        <a-button
          v-if="canTryOn"
          size="small"
          type="primary"
          :loading="trying"
          @click="$emit('try-on', item)"
        >
          <template #icon><EyeOutlined /></template>
          {{ t('core.themeStore.tryOn.action') }}
        </a-button>
        <a-button size="small" @click="$emit('open-detail', item)">
          {{ t('core.themeStore.featured.viewDetail') }}
        </a-button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.featured-collapsed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 12px;
  margin-bottom: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-tertiary);
}

.featured-collapsed-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.featured-collapsed-name {
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.featured-banner {
  display: grid;
  grid-template-columns: minmax(260px, 1.1fr) minmax(0, 1.2fr);
  min-height: 196px;
  margin-bottom: 16px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  background: var(--ant-color-bg-container);
}

.featured-banner--compact {
  grid-template-columns: 248px minmax(0, 1fr);
  min-height: 136px;
}

.featured-media {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--ant-color-bg-layout);
  cursor: pointer;
}

.featured-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.featured-placeholder {
  color: var(--ant-color-text-quaternary);
  font-size: 32px;
}

.featured-badge-wrap {
  position: absolute;
  top: 8px;
  left: 8px;
}

.featured-tag {
  margin-inline-end: 0;
}

.featured-info {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px;
}

.featured-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.featured-title-row {
  display: flex;
  min-width: 0;
  gap: 8px;
  align-items: center;
}

.featured-title {
  margin: 0;
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.featured-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.featured-desc {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 18px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.featured-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: auto;
  padding-top: 4px;
}

@media (max-width: 780px) {
  .featured-banner,
  .featured-banner--compact {
    grid-template-columns: minmax(0, 1fr);
  }

  .featured-media {
    aspect-ratio: 16 / 9;
  }
}
</style>
