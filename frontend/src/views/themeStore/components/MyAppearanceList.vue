<script setup lang="ts">
import { ref } from 'vue'
import { SkinOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import type { MyAppearanceItem } from '@/composables/useShareApi'
import { getMyAppearanceState, isInStore, type MyAppearanceState } from '../myAppearance'
import { formatOnlineAppearanceTime } from '../useOnlineAppearance'
import type { MyAppearanceStore } from '../useMyAppearances'
import AppearanceDescriptionModal from './AppearanceDescriptionModal.vue'

const props = defineProps<{
  store: MyAppearanceStore
}>()

const emit = defineEmits<{
  (event: 'upload-version', fileId: number): void
  (event: 'view-in-store', item: MyAppearanceItem): void
}>()

const STATE_COLORS: Record<MyAppearanceState['kind'], string> = {
  published: 'success',
  publishedPending: 'processing',
  pending: 'processing',
  rejected: 'error',
}

const { t } = useI18n()
const { items, loading, error, coverFor, load } = props.store

const editing = ref<MyAppearanceItem | null>(null)
const editOpen = ref(false)

const stateLabel = (state: MyAppearanceState): string => {
  switch (state.kind) {
    case 'published':
      return t('themeStore.mine.published', { version: state.published })
    case 'publishedPending':
      return t('themeStore.mine.publishedPending', {
        published: state.published,
        latest: state.latest,
      })
    case 'pending':
      return t('themeStore.mine.pending', { version: state.latest })
    case 'rejected':
      return state.published === null
        ? t('themeStore.mine.rejected', { version: state.latest })
        : t('themeStore.mine.publishedRejected', {
            published: state.published,
            latest: state.latest,
          })
  }
}

// 正常状态不标；归档、停用的文件不在商店里，要让作者知道
const fileStatusLabel = (status: string): string | null => {
  if (status === 'archived') return t('themeStore.mine.archived')
  if (status === 'disabled') return t('themeStore.mine.disabled')
  return null
}

const editDescription = (item: MyAppearanceItem): void => {
  editing.value = item
  editOpen.value = true
}
</script>

<template>
  <div class="mine-toolbar">
    <a-button :loading="loading" @click="load">
      {{ t('themeStore.refresh') }}
    </a-button>
  </div>
  <div v-if="loading && items.length === 0" class="mine-state">
    <a-spin size="large" :tip="t('themeStore.loading')" />
  </div>
  <div v-else-if="error" class="mine-state">
    <a-result status="warning" :title="t('themeStore.mine.loadFailed')" :sub-title="error">
      <template #extra>
        <a-button type="primary" @click="load">{{ t('themeStore.retry') }}</a-button>
      </template>
    </a-result>
  </div>
  <div v-else-if="items.length === 0" class="mine-state">
    <a-empty :description="t('themeStore.mine.empty')" />
  </div>
  <div v-else class="mine-grid">
    <div v-for="item in items" :key="item.fileId" class="mine-card">
      <span class="mine-cover">
        <img
          v-if="coverFor(item)"
          :src="coverFor(item)"
          :alt="item.displayName || item.fileKey"
          class="mine-cover-image"
        />
        <SkinOutlined v-else class="mine-cover-placeholder" />
        <a-tag :color="STATE_COLORS[getMyAppearanceState(item).kind]" class="mine-cover-tag">
          {{ stateLabel(getMyAppearanceState(item)) }}
        </a-tag>
      </span>
      <div class="mine-card-body">
        <span class="mine-name">
          {{ item.displayName || item.fileKey }}
          <a-tag v-if="fileStatusLabel(item.status)" class="mine-status-tag">
            {{ fileStatusLabel(item.status) }}
          </a-tag>
        </span>
        <span class="mine-meta">{{ formatOnlineAppearanceTime(item.updatedAt) }}</span>
        <span class="mine-description">
          {{ item.description || t('themeStore.noDescription') }}
        </span>
        <span
          v-if="getMyAppearanceState(item).kind === 'rejected' && item.latestReviewComment.trim()"
          class="mine-reject-reason"
        >
          {{ t('themeStore.mine.rejectReason', { reason: item.latestReviewComment.trim() }) }}
        </span>
        <div class="mine-actions">
          <a-button size="small" type="primary" @click="emit('upload-version', item.fileId)">
            {{ t('themeStore.mine.uploadVersion') }}
          </a-button>
          <a-button size="small" @click="editDescription(item)">
            {{ t('themeStore.mine.editDescription') }}
          </a-button>
          <a-button
            v-if="isInStore(item)"
            size="small"
            type="link"
            @click="emit('view-in-store', item)"
          >
            {{ t('themeStore.mine.viewInStore') }}
          </a-button>
        </div>
      </div>
    </div>
  </div>
  <AppearanceDescriptionModal v-model:open="editOpen" :item="editing" :store="store" />
</template>

<style scoped>
.mine-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.mine-state {
  display: flex;
  min-height: 320px;
  align-items: center;
  justify-content: center;
}

.mine-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.mine-card {
  display: flex;
  min-width: 0;
  overflow: hidden;
  flex-direction: column;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
}

.mine-cover {
  position: relative;
  display: flex;
  aspect-ratio: 16 / 10;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-bg-layout);
}

.mine-cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.mine-cover-placeholder {
  color: var(--ant-color-text-quaternary);
  font-size: 32px;
}

.mine-cover-tag {
  position: absolute;
  top: 8px;
  right: 8px;
  max-width: calc(100% - 16px);
  margin-inline-end: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mine-card-body {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  padding: 12px 14px 14px;
}

.mine-name {
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mine-status-tag {
  margin-inline: 6px 0;
  font-weight: 400;
}

.mine-meta {
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.mine-description,
.mine-reject-reason {
  display: -webkit-box;
  margin-top: 8px;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-line;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.mine-description {
  color: var(--ant-color-text-secondary);
}

.mine-reject-reason {
  color: var(--ant-color-error);
  -webkit-line-clamp: 3;
}

.mine-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: auto;
  padding-top: 12px;
}
</style>
