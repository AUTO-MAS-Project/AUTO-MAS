<script setup lang="ts">
import { SearchOutlined, SkinOutlined, UserOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import {
  formatOnlineAppearanceTime,
  getOnlineAppearanceStatus,
  type OnlineAppearanceStore,
} from '../useOnlineAppearance'

const props = defineProps<{
  store: OnlineAppearanceStore
}>()

const { t } = useI18n()
const {
  items,
  listLoading,
  listError,
  page,
  total,
  keyword,
  pageSize,
  coverFor,
  loadList,
  scheduleSearch,
  clearKeyword,
  openDetail,
} = props.store

const handleKeywordInput = (value: string): void => {
  keyword.value = value
  scheduleSearch()
}
</script>

<template>
  <div class="online-toolbar">
    <a-input
      :value="keyword"
      allow-clear
      :placeholder="t('themeStore.search')"
      @update:value="handleKeywordInput"
      @press-enter="loadList(1)"
    >
      <template #prefix><SearchOutlined /></template>
    </a-input>
    <a-button :loading="listLoading" @click="loadList(page)">
      {{ t('themeStore.refresh') }}
    </a-button>
  </div>
  <div v-if="listLoading" class="online-state">
    <a-spin size="large" :tip="t('themeStore.loading')" />
  </div>
  <div v-else-if="listError" class="online-state">
    <a-result status="warning" :title="t('themeStore.listFailed')" :sub-title="listError">
      <template #extra>
        <a-button type="primary" @click="loadList(page)">
          {{ t('themeStore.retry') }}
        </a-button>
      </template>
    </a-result>
  </div>
  <div v-else-if="items.length === 0" class="online-state">
    <a-empty :description="keyword.trim() ? t('themeStore.noMatch') : t('themeStore.empty')">
      <a-button v-if="keyword.trim()" @click="clearKeyword">
        {{ t('themeStore.clearSearch') }}
      </a-button>
    </a-empty>
  </div>
  <div v-else class="online-grid">
    <button
      v-for="item in items"
      :key="item.fileKey"
      type="button"
      class="online-card"
      @click="openDetail(item)"
    >
      <span class="online-cover">
        <img
          v-if="coverFor(item.fileKey, item.publishedVersionNo)"
          :src="coverFor(item.fileKey, item.publishedVersionNo)"
          :alt="item.displayName || item.fileKey"
          class="online-cover-image"
        />
        <SkinOutlined v-else class="online-cover-placeholder" />
        <a-tag
          v-if="getOnlineAppearanceStatus(item) === 'installed'"
          color="success"
          class="online-cover-tag"
        >
          {{ t('themeStore.installed') }}
        </a-tag>
        <a-tag
          v-else-if="getOnlineAppearanceStatus(item) === 'outdated'"
          color="warning"
          class="online-cover-tag"
        >
          {{ t('themeStore.installedOlder', { version: item.installed?.versionNo }) }}
        </a-tag>
      </span>
      <span class="online-card-body">
        <span class="online-name">{{ item.displayName || item.fileKey }}</span>
        <span class="online-meta">
          <span v-if="item.publishedVersionNo !== null">v{{ item.publishedVersionNo }}</span>
          <span class="online-owner">
            <UserOutlined />
            {{ item.ownerUsername || t('themeStore.unknownAuthor') }}
          </span>
          <span>{{ formatOnlineAppearanceTime(item.publishedAt || item.updatedAt) }}</span>
        </span>
        <span class="online-description">
          {{ item.description || t('themeStore.noDescription') }}
        </span>
      </span>
    </button>
  </div>
  <div v-if="!listLoading && !listError && total > pageSize" class="online-pagination">
    <a-pagination
      size="small"
      :current="page"
      :page-size="pageSize"
      :total="total"
      :show-size-changer="false"
      @change="loadList"
    />
  </div>
</template>

<style scoped>
.online-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  margin-bottom: 16px;
}

.online-state {
  display: flex;
  min-height: 320px;
  align-items: center;
  justify-content: center;
}

.online-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.online-card {
  display: flex;
  min-width: 0;
  overflow: hidden;
  flex-direction: column;
  padding: 0;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.online-card:hover,
.online-card:focus-visible {
  border-color: var(--ant-color-primary);
  outline: none;
}

.online-cover {
  position: relative;
  display: flex;
  aspect-ratio: 16 / 10;
  align-items: center;
  justify-content: center;
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

.online-cover-tag {
  position: absolute;
  top: 8px;
  right: 8px;
  margin-inline-end: 0;
}

.online-card-body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 12px 14px 14px;
}

.online-name {
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.online-meta {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 2px 12px;
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.online-owner {
  overflow: hidden;
  max-width: 100%;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.online-description {
  display: -webkit-box;
  margin-top: 8px;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-line;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.online-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
