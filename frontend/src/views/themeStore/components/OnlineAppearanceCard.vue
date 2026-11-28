<script setup lang="ts">
import { EyeOutlined, SkinOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { OnlineAppearanceItem, OnlineAppearancePrepareProgress } from '@/types/appearance'
import { formatDownloadCount } from '../storeFiltering'
import {
  formatOnlineAppearanceTime,
  formatPrepareProgressText,
  getOnlineAppearanceStatus,
} from '../useOnlineAppearance'

const props = defineProps<{
  item: OnlineAppearanceItem
  coverUrl?: string
  showCategoryBadge: boolean
  canTryOn: boolean
  isActive: boolean
  isTrying: boolean
  tryingLoading: boolean
  tryProgress?: OnlineAppearancePrepareProgress | null
}>()

const emit = defineEmits<{
  open: [item: OnlineAppearanceItem]
  'try-on': [item: OnlineAppearanceItem]
}>()

const { t } = useI18n()

const handleTryOn = (event: MouseEvent): void => {
  event.stopPropagation()
  emit('try-on', props.item)
}
</script>

<template>
  <article
    class="online-card"
    :class="{ 'online-card--trying': isTrying }"
    tabindex="0"
    role="button"
    @click="emit('open', item)"
    @keydown.enter.prevent="emit('open', item)"
    @keydown.space.prevent="emit('open', item)"
  >
    <div class="online-cover">
      <img
        v-if="coverUrl"
        :src="coverUrl"
        :alt="item.displayName || item.fileKey"
        loading="lazy"
        class="online-cover-image"
      />
      <SkinOutlined v-else class="online-cover-placeholder" />

      <span v-if="showCategoryBadge && item.categoryKey" class="online-cover-cat">
        {{ t(`core.themeStore.categories.${item.categoryKey}`) }}
      </span>

      <a-tag v-if="isTrying" color="processing" class="online-cover-tag">
        {{ t('core.themeStore.tryOn.tryingBadge') }}
      </a-tag>
      <a-tag v-else-if="isActive" color="success" class="online-cover-tag">
        {{ t('core.themeStore.activeNow') }}
      </a-tag>
      <a-tag
        v-else-if="getOnlineAppearanceStatus(item) === 'outdated'"
        color="warning"
        class="online-cover-tag"
      >
        {{ t('core.themeStore.installedOlder', { version: item.installed?.versionNo }) }}
      </a-tag>
      <a-tag
        v-else-if="getOnlineAppearanceStatus(item) === 'installed'"
        color="blue"
        class="online-cover-tag"
      >
        {{ t('core.themeStore.installed') }}
      </a-tag>
      <a-tag v-else-if="(item.tags?.length ?? 0) > 0" color="purple" class="online-cover-tag">
        {{ item.tags!.length > 1 ? `${item.tags![0]} +${item.tags!.length - 1}` : item.tags![0] }}
      </a-tag>

      <div v-if="tryingLoading" class="online-cover-progress" @click.stop>
        <div class="online-cover-progress-text">{{ formatPrepareProgressText(tryProgress) }}</div>
        <a-progress
          :percent="tryProgress?.percent ?? 0"
          :status="tryProgress?.phase === 'verifying' ? 'active' : 'normal'"
          :show-info="false"
          size="small"
          class="online-cover-progress-bar"
        />
      </div>
      <div v-else-if="canTryOn" class="online-cover-overlay">
        <a-button size="small" type="primary" :loading="tryingLoading" @click="handleTryOn">
          <template #icon><EyeOutlined /></template>
          {{ t('core.themeStore.tryOn.action') }}
        </a-button>
      </div>
    </div>

    <div class="online-card-body">
      <div class="online-card-top">
        <span class="online-name">{{ item.displayName || item.fileKey }}</span>
        <span v-if="(item.downloadCount ?? 0) > 0" class="online-downloads">
          ↓ {{ formatDownloadCount(item.downloadCount) }}
        </span>
      </div>
      <div class="online-meta">
        <span class="online-owner">
          @{{ item.ownerUsername || t('core.themeStore.unknownAuthor') }}
        </span>
        <span class="online-meta-right">
          <span v-if="item.publishedVersionNo !== null">v{{ item.publishedVersionNo }}</span>
          <span>{{ formatOnlineAppearanceTime(item.publishedAt || item.updatedAt) }}</span>
        </span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.online-card {
  display: flex;
  min-width: 0;
  overflow: hidden;
  flex-direction: column;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}

.online-card:hover,
.online-card:focus-visible {
  border-color: var(--ant-color-primary);
  outline: none;
}

.online-card--trying {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

.online-cover {
  position: relative;
  display: flex;
  aspect-ratio: 16 / 10;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--ant-color-bg-layout);
}

.online-cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.online-cover-placeholder {
  color: var(--ant-color-text-quaternary);
  font-size: 32px;
}

.online-cover-cat {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 1px 7px;
  border-radius: 5px;
  background: var(--ant-color-bg-mask);
  color: var(--ant-color-text-light-solid);
  font-size: 11px;
  font-weight: 500;
  line-height: 18px;
}

.online-cover-tag {
  position: absolute;
  top: 8px;
  right: 8px;
  margin-inline-end: 0;
}

.online-cover-overlay {
  position: absolute;
  right: 8px;
  bottom: 8px;
  opacity: 0;
  transition: opacity 0.16s ease;
}

.online-cover-progress {
  position: absolute;
  right: 8px;
  bottom: 8px;
  left: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-elevated);
  box-shadow: var(--ant-box-shadow-tertiary);
}

.online-cover-progress-text {
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  line-height: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.online-cover-progress-bar {
  margin: 0;
  line-height: 1;
}

.online-card:hover .online-cover-overlay,
.online-card:focus-within .online-cover-overlay,
.online-card--trying .online-cover-overlay {
  opacity: 1;
}

.online-card-body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px 12px;
}

.online-card-top {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.online-name {
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.online-downloads {
  flex: none;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.online-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 20px;
}

.online-owner {
  overflow: hidden;
  min-width: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.online-meta-right {
  display: inline-flex;
  flex: none;
  gap: 8px;
  align-items: center;
}
</style>
