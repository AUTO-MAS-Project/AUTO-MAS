<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  ClockCircleOutlined,
  DownloadOutlined,
  EyeOutlined,
  UploadOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import { useAppearanceTryOnStore } from '@/stores/appearanceTryOn'
import { formatDownloadCount } from '../storeFiltering'
import {
  formatAppearanceFileSize,
  formatOnlineAppearanceTime,
  getOnlineAppearanceStatus,
  type OnlineAppearanceStore,
} from '../useOnlineAppearance'
import type { MyAppearanceStore } from '../useMyAppearances'
import type { ShareAccount } from '../useShareAccount'
import OnlineAppearancePreviewBox from './OnlineAppearancePreviewBox.vue'

const props = defineProps<{
  store: OnlineAppearanceStore
  account: ShareAccount
  mine: MyAppearanceStore
}>()

const emit = defineEmits<{
  (event: 'upload-version', fileId: number): void
}>()

const { t } = useI18n()
const { persistedAppearance } = useTheme()
const tryOnStore = useAppearanceTryOnStore()

const {
  detailOpen,
  detailItem,
  versions,
  detailLoading,
  detailError,
  selectedVersionNo,
  detailCover,
  prepared,
  preparing,
  prepareError,
  installing,
  tryingFileKey,
  retryDetail,
  selectVersion,
  prepareSelected,
  install,
  tryOnItem,
  backToList,
} = props.store

const { authorized, state: accountState } = props.account
const locatingOwnFile = ref(false)

// 严格避让 Electron 顶部 32px 标题栏与窗口控制按钮。
const drawerRootStyle = computed(() => ({
  top: '32px',
  height: 'calc(100vh - 32px)',
}))

const isThemeDetail = computed(() => (detailItem.value?.categoryKey ?? 'theme') === 'theme')
const isOwner = computed(
  () =>
    authorized.value &&
    Boolean(detailItem.value?.ownerUsername) &&
    detailItem.value?.ownerUsername === accountState.value.username
)
const isActiveInstalled = computed(() =>
  Boolean(
    detailItem.value?.installed &&
    persistedAppearance.value?.id === detailItem.value.installed.appearanceId
  )
)

const versionOptions = computed(() =>
  versions.value.map(version => ({
    value: version.versionNo,
    label: [
      `v${version.versionNo}`,
      formatAppearanceFileSize(version.fileSize),
      formatOnlineAppearanceTime(version.createdAt),
      detailItem.value?.installed?.versionNo === version.versionNo
        ? t('core.themeStore.installed')
        : '',
    ]
      .filter(Boolean)
      .join(' · '),
  }))
)

const uploadVersion = async (): Promise<void> => {
  const fileKey = detailItem.value?.fileKey
  if (!fileKey || locatingOwnFile.value) return
  locatingOwnFile.value = true
  try {
    let own = props.mine.findByFileKey(fileKey)
    if (!own) {
      await props.mine.load()
      own = props.mine.findByFileKey(fileKey)
    }
    if (!own) {
      message.warning(props.mine.error.value || t('core.themeStore.mine.notFound'))
      return
    }
    emit('upload-version', own.fileId)
  } finally {
    locatingOwnFile.value = false
  }
}

const handleVersionChange = (value: SelectValue): void => {
  if (typeof value === 'number') selectVersion(value)
}

const handleTryOn = (): void => {
  if (!detailItem.value) return
  void tryOnItem(detailItem.value, selectedVersionNo.value ?? undefined)
}
</script>

<template>
  <a-drawer
    :open="detailOpen"
    :width="468"
    placement="right"
    :closable="!installing"
    :mask-closable="!installing"
    :keyboard="!installing"
    :root-style="drawerRootStyle"
    :z-index="900"
    @close="backToList"
  >
    <template #title>
      <div v-if="detailItem" class="drawer-title-wrap">
        <a-tag v-if="detailItem.categoryKey" color="blue" class="drawer-title-tag">
          {{ t(`core.themeStore.categories.${detailItem.categoryKey}`) }}
        </a-tag>
        <span class="drawer-title-text">{{ detailItem.displayName || detailItem.fileKey }}</span>
      </div>
    </template>

    <div v-if="detailLoading" class="drawer-state">
      <a-spin size="large" :tip="t('core.themeStore.loading')" />
    </div>
    <div v-else-if="detailError" class="drawer-state">
      <a-result
        status="warning"
        :title="t('core.themeStore.detailFailed')"
        :sub-title="detailError"
      >
        <template #extra>
          <a-button type="primary" @click="retryDetail">{{ t('core.themeStore.retry') }}</a-button>
        </template>
      </a-result>
    </div>
    <div v-else-if="detailItem" class="drawer-content">
      <OnlineAppearancePreviewBox
        :display-name="detailItem.displayName || detailItem.fileKey"
        :detail-cover="detailCover"
        :prepared="prepared"
        :preparing="preparing"
        :prepare-error="prepareError"
        :has-versions="versions.length > 0"
        @prepare="prepareSelected"
      />

      <div class="drawer-meta-row">
        <span>
          <UserOutlined />
          {{ detailItem.ownerUsername || t('core.themeStore.unknownAuthor') }}
        </span>
        <span>
          <ClockCircleOutlined />
          {{ formatOnlineAppearanceTime(detailItem.publishedAt || detailItem.updatedAt) }}
        </span>
        <span v-if="(detailItem.downloadCount ?? 0) > 0">
          {{
            t('core.themeStore.downloads', { count: formatDownloadCount(detailItem.downloadCount) })
          }}
        </span>
      </div>

      <div class="drawer-status-tags">
        <a-tag v-if="isActiveInstalled" color="success">{{ t('core.themeStore.activeNow') }}</a-tag>
        <a-tag v-else-if="getOnlineAppearanceStatus(detailItem) === 'outdated'" color="warning">
          {{ t('core.themeStore.installedOlder', { version: detailItem.installed?.versionNo }) }}
        </a-tag>
        <a-tag v-else-if="getOnlineAppearanceStatus(detailItem) === 'installed'" color="blue">
          {{ t('core.themeStore.installed') }}
        </a-tag>
        <a-tag v-for="tag in detailItem.tags ?? []" :key="tag" color="purple">{{ tag }}</a-tag>
      </div>

      <p class="drawer-description">
        {{ detailItem.description || t('core.themeStore.noDescription') }}
      </p>

      <div class="drawer-section">
        <div class="drawer-section-label">{{ t('core.themeStore.version') }}</div>
        <a-select
          :value="selectedVersionNo ?? undefined"
          :options="versionOptions"
          :disabled="installing || preparing || versions.length === 0"
          class="drawer-version-select"
          @change="handleVersionChange"
        />
        <div v-if="versions.length > 0" class="drawer-version-list">
          <div
            v-for="ver in versions"
            :key="ver.versionNo"
            class="drawer-version-card"
            :class="{ 'is-selected': ver.versionNo === selectedVersionNo }"
            @click="selectVersion(ver.versionNo)"
          >
            <div class="drawer-version-head">
              <strong>v{{ ver.versionNo }}</strong>
              <span class="drawer-version-meta">
                {{ formatAppearanceFileSize(ver.fileSize) }} ·
                {{ formatOnlineAppearanceTime(ver.createdAt) }}
              </span>
            </div>
            <div class="drawer-version-note">
              {{ ver.changeNote || t('core.themeStore.noChangeNote') }}
            </div>
          </div>
        </div>
      </div>

      <dl v-if="prepared" class="drawer-facts">
        <dt>{{ t('core.themeStore.packageName') }}</dt>
        <dd>{{ prepared.appearance.name }}</dd>
        <dt>ID</dt>
        <dd class="drawer-mono">{{ prepared.appearance.id }}</dd>
        <template v-if="prepared.appearance.mode">
          <dt>{{ t('core.themeStore.mode') }}</dt>
          <dd>
            {{
              prepared.appearance.mode === 'dark'
                ? t('core.setting.themeMode.dark')
                : t('core.setting.themeMode.light')
            }}
          </dd>
        </template>
        <template v-if="prepared.existing">
          <dt>{{ t('core.themeStore.localCopy') }}</dt>
          <dd>{{ prepared.existing.name }}</dd>
        </template>
      </dl>

      <a-alert
        v-if="prepared?.appearance.hasBundledMascot"
        type="info"
        show-icon
        :message="t('core.themeStore.tryOn.drawerMascotNote')"
      />
    </div>

    <template #footer>
      <div class="drawer-footer" :class="{ 'drawer-footer--dock-pad': tryOnStore.active }">
        <div class="drawer-footer-left">
          <a-button v-if="isOwner" :loading="locatingOwnFile" @click="uploadVersion">
            <template #icon><UploadOutlined /></template>
            {{ t('core.themeStore.mine.uploadVersion') }}
          </a-button>
        </div>
        <div class="drawer-footer-right">
          <a-button
            v-if="isThemeDetail"
            :loading="tryingFileKey === detailItem?.fileKey"
            :disabled="installing || detailLoading || selectedVersionNo === null"
            @click="handleTryOn"
          >
            <template #icon><EyeOutlined /></template>
            {{ t('core.themeStore.tryOn.action') }}
          </a-button>
          <a-button
            type="primary"
            :loading="installing"
            :disabled="preparing || detailLoading || selectedVersionNo === null"
            @click="install"
          >
            <template #icon><DownloadOutlined /></template>
            {{ t('core.themeStore.install') }}
          </a-button>
        </div>
      </div>
    </template>
  </a-drawer>
</template>

<style scoped>
.drawer-title-wrap {
  display: flex;
  min-width: 0;
  gap: 8px;
  align-items: center;
}

.drawer-title-tag {
  margin-inline-end: 0;
  flex: none;
}

.drawer-title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-state {
  display: flex;
  min-height: 280px;
  align-items: center;
  justify-content: center;
}

.drawer-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.drawer-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.drawer-status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.drawer-description {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 20px;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.drawer-section-label {
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
}

.drawer-version-select {
  width: 100%;
}

.drawer-version-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.drawer-version-card {
  padding: 8px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-tertiary);
  cursor: pointer;
}

.drawer-version-card.is-selected {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg);
}

.drawer-version-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.drawer-version-meta {
  color: var(--ant-color-text-tertiary);
}

.drawer-version-note {
  margin-top: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.drawer-facts {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 6px 12px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-tertiary);
  font-size: 12px;
}

.drawer-facts dt {
  color: var(--ant-color-text-secondary);
}

.drawer-facts dd {
  margin: 0;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}

.drawer-mono {
  font-family: var(--font-monospace);
}

.drawer-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.drawer-footer--dock-pad {
  padding-bottom: 56px;
}

.drawer-footer-left,
.drawer-footer-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
