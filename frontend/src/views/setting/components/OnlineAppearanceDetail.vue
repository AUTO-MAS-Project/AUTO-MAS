<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeftOutlined, ClockCircleOutlined, UserOutlined } from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'

import {
  formatAppearanceFileSize,
  formatOnlineAppearanceTime,
  type OnlineAppearanceStore,
} from '../useOnlineAppearance'

const props = defineProps<{
  store: OnlineAppearanceStore
}>()

const { t } = useI18n()
const {
  detailItem,
  versions,
  detailLoading,
  detailError,
  selectedVersionNo,
  selectedVersion,
  prepared,
  preparing,
  prepareError,
  installing,
  retryDetail,
  selectVersion,
  prepareSelected,
  install,
  backToList,
} = props.store

const versionOptions = computed(() =>
  versions.value.map(version => ({
    value: version.versionNo,
    label: [
      `v${version.versionNo}`,
      formatAppearanceFileSize(version.fileSize),
      formatOnlineAppearanceTime(version.createdAt),
      detailItem.value?.installed?.versionNo === version.versionNo
        ? t('setting.onlineAppearance.installed')
        : '',
    ]
      .filter(Boolean)
      .join(' · '),
  }))
)

// 包里没有预览图时，用包内 tokens 画一个最小的界面示意；颜色已由主进程校验为 #rrggbb。
const swatchStyle = computed(() => {
  const tokens = prepared.value?.appearance.tokens
  const dark = prepared.value?.appearance.mode === 'dark'
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

const handleVersionChange = (value: SelectValue): void => {
  if (typeof value === 'number') selectVersion(value)
}
</script>

<template>
  <div class="online-detail-bar">
    <a-button type="text" :disabled="installing" @click="backToList">
      <template #icon><ArrowLeftOutlined /></template>
      {{ t('setting.onlineAppearance.back') }}
    </a-button>
  </div>
  <div class="online-scroll">
    <div v-if="detailLoading" class="online-state">
      <a-spin size="large" :tip="t('setting.onlineAppearance.loading')" />
    </div>
    <div v-else-if="detailError" class="online-state">
      <a-result
        status="warning"
        :title="t('setting.onlineAppearance.detailFailed')"
        :sub-title="detailError"
      >
        <template #extra>
          <a-button type="primary" @click="retryDetail">
            {{ t('setting.onlineAppearance.retry') }}
          </a-button>
        </template>
      </a-result>
    </div>
    <div v-else-if="detailItem" class="online-detail">
      <section class="online-preview">
        <div v-if="preparing" class="online-preview-state">
          <a-spin :tip="t('setting.onlineAppearance.preparing')" />
        </div>
        <div v-else-if="prepareError" class="online-preview-state">
          <a-result status="warning" :sub-title="prepareError">
            <template #extra>
              <a-button @click="prepareSelected">
                {{ t('setting.onlineAppearance.retry') }}
              </a-button>
            </template>
          </a-result>
        </div>
        <template v-else-if="prepared">
          <img
            v-if="prepared.appearance.previewUrl"
            :src="prepared.appearance.previewUrl"
            :alt="prepared.appearance.name"
            class="online-preview-image"
          />
          <div v-else class="online-swatch" :style="swatchStyle">
            <span class="swatch-sider" />
            <span class="swatch-card">
              <span class="swatch-line strong" />
              <span class="swatch-line" />
              <span class="swatch-button" />
            </span>
          </div>
        </template>
        <div v-else-if="versions.length === 0" class="online-preview-state">
          <a-empty :description="t('setting.onlineAppearance.noVersions')" />
        </div>
        <div v-else class="online-preview-state">
          <a-button @click="prepareSelected">
            {{ t('setting.onlineAppearance.downloadPreview') }}
          </a-button>
        </div>
      </section>

      <section class="online-info">
        <h3 class="online-info-title">{{ detailItem.displayName || detailItem.fileKey }}</h3>
        <div class="online-meta">
          <span>
            <UserOutlined />
            {{ detailItem.ownerUsername || t('setting.onlineAppearance.unknownAuthor') }}
          </span>
          <span>
            <ClockCircleOutlined />
            {{ formatOnlineAppearanceTime(detailItem.publishedAt || detailItem.updatedAt) }}
          </span>
        </div>
        <p class="online-description">
          {{ detailItem.description || t('setting.onlineAppearance.noDescription') }}
        </p>

        <div class="online-field">
          <span class="online-field-label">{{ t('setting.onlineAppearance.version') }}</span>
          <a-select
            :value="selectedVersionNo ?? undefined"
            :options="versionOptions"
            :disabled="installing || preparing || versions.length === 0"
            class="online-version-select"
            @change="handleVersionChange"
          />
        </div>
        <p v-if="selectedVersion?.changeNote" class="online-change-note">
          {{ selectedVersion.changeNote }}
        </p>

        <dl v-if="prepared" class="online-facts">
          <dt>{{ t('setting.onlineAppearance.packageName') }}</dt>
          <dd>{{ prepared.appearance.name }}</dd>
          <dt>ID</dt>
          <dd class="online-mono">{{ prepared.appearance.id }}</dd>
          <dt>{{ t('setting.onlineAppearance.mode') }}</dt>
          <dd>
            {{
              prepared.appearance.mode === 'dark'
                ? t('setting.themeMode.dark')
                : t('setting.themeMode.light')
            }}
          </dd>
          <template v-if="prepared.existing">
            <dt>{{ t('setting.onlineAppearance.localCopy') }}</dt>
            <dd>{{ prepared.existing.name }}</dd>
          </template>
        </dl>

        <div class="online-actions">
          <a-button
            type="primary"
            :loading="installing"
            :disabled="preparing || !prepared"
            @click="install"
          >
            {{ t('setting.onlineAppearance.install') }}
          </a-button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.online-detail-bar {
  margin: -4px 0 8px -8px;
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

.online-detail {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.online-preview {
  display: flex;
  aspect-ratio: 16 / 10;
  min-height: 0;
  overflow: hidden;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-layout);
}

.online-preview-state {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.online-preview-state :deep(.ant-result) {
  padding: 0;
}

.online-preview-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.online-swatch {
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
  padding: 16px;
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
  height: 22px;
  margin-top: auto;
  border-radius: var(--swatch-radius);
  background: var(--swatch-primary);
}

.online-info {
  min-width: 0;
}

.online-info-title {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.online-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.online-description,
.online-change-note {
  margin: 8px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.online-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 16px;
}

.online-field-label,
.online-facts dt {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.online-version-select {
  width: 100%;
}

.online-facts {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 6px 12px;
  margin: 16px 0 0;
}

.online-facts dd {
  margin: 0;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}

.online-mono {
  font-family: var(--font-monospace);
}

.online-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 24px;
}

@media (max-width: 760px) {
  .online-detail {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
