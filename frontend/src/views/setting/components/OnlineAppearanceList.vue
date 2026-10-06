<script setup lang="ts">
import {
  ClockCircleOutlined,
  RightOutlined,
  SearchOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
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
      :placeholder="t('setting.onlineAppearance.search')"
      @update:value="handleKeywordInput"
      @press-enter="loadList(1)"
    >
      <template #prefix><SearchOutlined /></template>
    </a-input>
    <a-button :loading="listLoading" @click="loadList(page)">
      {{ t('setting.onlineAppearance.refresh') }}
    </a-button>
  </div>
  <div class="online-scroll">
    <div v-if="listLoading" class="online-state">
      <a-spin size="large" :tip="t('setting.onlineAppearance.loading')" />
    </div>
    <div v-else-if="listError" class="online-state">
      <a-result
        status="warning"
        :title="t('setting.onlineAppearance.listFailed')"
        :sub-title="listError"
      >
        <template #extra>
          <a-button type="primary" @click="loadList(page)">
            {{ t('setting.onlineAppearance.retry') }}
          </a-button>
        </template>
      </a-result>
    </div>
    <div v-else-if="items.length === 0" class="online-state">
      <a-empty
        :description="
          keyword.trim()
            ? t('setting.onlineAppearance.noMatch')
            : t('setting.onlineAppearance.empty')
        "
      >
        <a-button v-if="keyword.trim()" @click="clearKeyword">
          {{ t('setting.onlineAppearance.clearSearch') }}
        </a-button>
      </a-empty>
    </div>
    <div v-else class="online-list">
      <button
        v-for="item in items"
        :key="item.fileKey"
        type="button"
        class="online-row"
        @click="openDetail(item)"
      >
        <span class="online-row-copy">
          <span class="online-row-title">
            <span class="online-name">{{ item.displayName || item.fileKey }}</span>
            <a-tag v-if="getOnlineAppearanceStatus(item) === 'installed'" color="success">
              {{ t('setting.onlineAppearance.installed') }}
            </a-tag>
            <a-tag v-else-if="getOnlineAppearanceStatus(item) === 'outdated'" color="warning">
              {{
                t('setting.onlineAppearance.installedOlder', {
                  version: item.installed?.versionNo,
                })
              }}
            </a-tag>
          </span>
          <span class="online-meta">
            <span v-if="item.publishedVersionNo !== null">v{{ item.publishedVersionNo }}</span>
            <span>
              <UserOutlined />
              {{ item.ownerUsername || t('setting.onlineAppearance.unknownAuthor') }}
            </span>
            <span>
              <ClockCircleOutlined />
              {{ formatOnlineAppearanceTime(item.publishedAt || item.updatedAt) }}
            </span>
          </span>
          <span class="online-description">
            {{ item.description || t('setting.onlineAppearance.noDescription') }}
          </span>
        </span>
        <RightOutlined class="online-row-arrow" />
      </button>
    </div>
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

.online-scroll {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
}

.online-state {
  display: flex;
  height: 100%;
  min-height: 200px;
  align-items: center;
  justify-content: center;
}

.online-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.online-row {
  display: flex;
  width: 100%;
  min-width: 0;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.online-row:hover,
.online-row:focus-visible {
  border-color: var(--ant-color-primary);
  outline: none;
}

.online-row-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.online-row-title {
  display: flex;
  min-width: 0;
  gap: 8px;
  align-items: center;
}

.online-name {
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.online-row-title :deep(.ant-tag) {
  margin-inline-end: 0;
}

.online-row-arrow {
  color: var(--ant-color-text-tertiary);
}

.online-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
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
  margin-top: 12px;
}
</style>
