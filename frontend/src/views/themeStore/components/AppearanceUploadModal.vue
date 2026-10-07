<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { FileZipOutlined, PictureOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import { useShareApi, type AppearanceUploadRecord } from '@/composables/useShareApi'
import type { OnlineAppearancePreview } from '@/types/appearance'
import { formatAppearanceFileSize } from '../useOnlineAppearance'
import type { ShareAccount } from '../useShareAccount'
import ThemeStoreAccount from './ThemeStoreAccount.vue'

const props = defineProps<{
  open: boolean
  account: ShareAccount
}>()

const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'uploaded'): void
}>()

const DISPLAY_NAME_MAX = 60
const DESCRIPTION_MAX = 2000
const CHANGE_NOTE_MAX = 500

const { t } = useI18n()
const logger = window.electronAPI.getLogger('主题商店')
const { uploadAppearance, listAppearanceUploads } = useShareApi()
const { authorized, refresh: refreshAccount } = props.account

const zipPath = ref('')
const inspecting = ref(false)
const inspectError = ref<string | null>(null)
const packageInfo = ref<{ appearance: OnlineAppearancePreview; fileSize: number } | null>(null)
const coverPath = ref<string | null>(null)
const coverPreviewUrl = ref<string | null>(null)
const uploads = ref<AppearanceUploadRecord[]>([])
const target = ref<'version' | 'new'>('new')
const submitting = ref(false)
const form = reactive({ displayName: '', description: '', changeNote: '' })

const fileName = (value: string): string => value.split(/[\\/]/).pop() ?? value

const previousUpload = computed(() =>
  packageInfo.value
    ? (uploads.value.find(item => item.appearanceId === packageInfo.value?.appearance.id) ?? null)
    : null
)

const packagePreview = computed(() => packageInfo.value?.appearance.previewUrl)
const coverImage = computed(() =>
  coverPath.value ? coverPreviewUrl.value : (packagePreview.value ?? null)
)
const hasCover = computed(() => Boolean(coverPath.value || packagePreview.value))
const canSubmit = computed(
  () =>
    authorized.value &&
    Boolean(packageInfo.value) &&
    hasCover.value &&
    (target.value === 'version' || form.displayName.trim().length > 0) &&
    !submitting.value
)

const reset = (): void => {
  zipPath.value = ''
  inspecting.value = false
  inspectError.value = null
  packageInfo.value = null
  coverPath.value = null
  coverPreviewUrl.value = null
  target.value = 'new'
  form.displayName = ''
  form.description = ''
  form.changeNote = ''
}

const loadUploads = async (): Promise<void> => {
  if (!authorized.value) {
    uploads.value = []
    return
  }
  uploads.value = await listAppearanceUploads()
}

const pickPackage = async (): Promise<void> => {
  const paths = await window.electronAPI.selectFile([
    { name: t('themeStore.upload.packageFilter'), extensions: ['zip'] },
  ])
  const picked = paths[0]
  if (!picked) return
  inspecting.value = true
  inspectError.value = null
  try {
    const result = await window.electronAPI.inspectLocalAppearance?.(picked)
    if (!result?.success || !result.appearance) {
      packageInfo.value = null
      zipPath.value = ''
      inspectError.value = result?.error || t('themeStore.upload.invalidPackage')
      return
    }
    zipPath.value = picked
    packageInfo.value = { appearance: result.appearance, fileSize: result.fileSize ?? 0 }
    form.displayName = form.displayName || result.appearance.name.slice(0, DISPLAY_NAME_MAX)
    form.description =
      form.description || (result.appearance.description ?? '').slice(0, DESCRIPTION_MAX)
    target.value = previousUpload.value ? 'version' : 'new'
  } catch (error) {
    logger.error(`读取外观包失败: ${error instanceof Error ? error.message : String(error)}`)
    inspectError.value = t('themeStore.upload.invalidPackage')
  } finally {
    inspecting.value = false
  }
}

const pickCover = async (): Promise<void> => {
  const paths = await window.electronAPI.selectFile([
    { name: t('themeStore.upload.coverFilter'), extensions: ['png', 'jpg', 'jpeg', 'webp'] },
  ])
  const picked = paths[0]
  if (!picked) return
  // 主进程按上传时同样的规则先查一遍（≤2 MB、PNG / JPEG / WebP），不合格就不采用。
  const result = await window.electronAPI.inspectAppearanceCover?.(picked)
  if (!result?.success || !result.dataUrl) {
    message.error(result?.error || t('themeStore.upload.invalidCover'))
    return
  }
  coverPath.value = picked
  coverPreviewUrl.value = result.dataUrl
}

const usePackageCover = (): void => {
  coverPath.value = null
  coverPreviewUrl.value = null
}

const close = (): void => {
  if (submitting.value) return
  emit('update:open', false)
}

const submit = async (): Promise<void> => {
  if (!canSubmit.value || !packageInfo.value) return
  submitting.value = true
  try {
    const result = await uploadAppearance({
      zipPath: zipPath.value,
      displayName: form.displayName.trim(),
      description: form.description.trim(),
      changeNote: form.changeNote.trim(),
      fileId: target.value === 'version' ? (previousUpload.value?.fileId ?? null) : null,
      coverPath: coverPath.value,
    })
    if (!result.ok) {
      // 令牌过期时刷新一次登录状态，界面回到「登录分享站」
      if (result.code === 401) await refreshAccount()
      // 站上那个文件已经删了或不归这个账号：本机记录作废，改成按新外观上传
      if (target.value === 'version' && (result.code === 403 || result.code === 404)) {
        const goneId = previousUpload.value?.fileId
        uploads.value = uploads.value.filter(item => item.fileId !== goneId)
        target.value = 'new'
        message.warning(t('themeStore.upload.versionTargetGone'))
        return
      }
      message.error(result.message || t('themeStore.upload.failed'))
      return
    }
    message.success(
      result.data?.reviewStatus === 'approved'
        ? t('themeStore.upload.published')
        : t('themeStore.upload.submitted')
    )
    emit('uploaded')
    emit('update:open', false)
  } finally {
    submitting.value = false
  }
}

watch(
  () => props.open,
  isOpen => {
    if (isOpen) void loadUploads()
  },
  { immediate: true }
)

watch(authorized, isAuthorized => {
  if (isAuthorized && props.open) void loadUploads()
})
</script>

<template>
  <a-modal
    :open="open"
    :width="640"
    :z-index="90"
    :style="{ top: '32px' }"
    :title="t('themeStore.upload.title')"
    :closable="!submitting"
    :keyboard="!submitting"
    :mask-closable="!submitting"
    :after-close="reset"
    @cancel="close"
  >
    <div class="upload-body">
      <a-alert
        v-if="!authorized"
        type="info"
        show-icon
        :message="t('themeStore.upload.loginRequired')"
      >
        <template #description>
          <ThemeStoreAccount :account="account" class="upload-account" />
        </template>
      </a-alert>

      <section class="upload-section">
        <div class="upload-label">{{ t('themeStore.upload.package') }}</div>
        <div class="upload-file-row">
          <a-button :loading="inspecting" :disabled="submitting" @click="pickPackage">
            <template #icon><FileZipOutlined /></template>
            {{ zipPath ? t('themeStore.upload.repick') : t('themeStore.upload.pick') }}
          </a-button>
          <span v-if="zipPath" class="upload-file-name">
            {{ fileName(zipPath) }} · {{ formatAppearanceFileSize(packageInfo?.fileSize ?? 0) }}
          </span>
        </div>
        <a-alert v-if="inspectError" type="error" show-icon :message="inspectError" />
        <div v-if="packageInfo" class="upload-package">
          <span class="upload-package-id">ID {{ packageInfo.appearance.id }}</span>
          <span>
            {{
              packageInfo.appearance.mode === 'dark'
                ? t('setting.themeMode.dark')
                : t('setting.themeMode.light')
            }}
          </span>
        </div>
      </section>

      <section v-if="packageInfo" class="upload-section">
        <div class="upload-label">{{ t('themeStore.upload.cover') }}</div>
        <div class="upload-cover">
          <div class="upload-cover-frame">
            <img
              v-if="coverImage"
              :src="coverImage"
              :alt="packageInfo.appearance.name"
              class="upload-cover-image"
            />
            <PictureOutlined v-else class="upload-cover-placeholder" />
          </div>
          <div class="upload-cover-actions">
            <span v-if="coverPath" class="upload-file-name">{{ fileName(coverPath) }}</span>
            <span v-else-if="packagePreview" class="upload-hint">
              {{ t('themeStore.upload.coverFromPackage') }}
            </span>
            <span v-else class="upload-hint upload-hint-warning">
              {{ t('themeStore.upload.coverRequired') }}
            </span>
            <span class="upload-cover-buttons">
              <a-button size="small" :disabled="submitting" @click="pickCover">
                {{ t('themeStore.upload.pickCover') }}
              </a-button>
              <a-button
                v-if="coverPath && packagePreview"
                size="small"
                type="link"
                :disabled="submitting"
                @click="usePackageCover"
              >
                {{ t('themeStore.upload.usePackageCover') }}
              </a-button>
            </span>
            <span class="upload-hint">{{ t('themeStore.upload.coverSpec') }}</span>
          </div>
        </div>
      </section>

      <a-form v-if="packageInfo" layout="vertical" class="upload-form">
        <a-form-item v-if="previousUpload" :label="t('themeStore.upload.target')">
          <a-radio-group v-model:value="target" :disabled="submitting">
            <a-radio value="version">
              {{ t('themeStore.upload.asVersion', { name: previousUpload.displayName }) }}
            </a-radio>
            <a-radio value="new">{{ t('themeStore.upload.asNew') }}</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="target === 'new'" :label="t('themeStore.upload.name')" required>
          <a-input
            v-model:value="form.displayName"
            :maxlength="DISPLAY_NAME_MAX"
            show-count
            :disabled="submitting"
          />
        </a-form-item>
        <a-form-item v-if="target === 'new'" :label="t('themeStore.upload.description')">
          <a-textarea
            v-model:value="form.description"
            :maxlength="DESCRIPTION_MAX"
            :auto-size="{ minRows: 2, maxRows: 5 }"
            :disabled="submitting"
          />
        </a-form-item>
        <a-form-item :label="t('themeStore.upload.changeNote')">
          <a-input
            v-model:value="form.changeNote"
            :maxlength="CHANGE_NOTE_MAX"
            :disabled="submitting"
          />
        </a-form-item>
      </a-form>
    </div>

    <template #footer>
      <a-button :disabled="submitting" @click="close">{{ t('common.cancel') }}</a-button>
      <a-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
        {{ t('themeStore.upload.submit') }}
      </a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.upload-body {
  display: flex;
  max-height: calc(100vh - 220px);
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.upload-account {
  justify-content: flex-start;
  margin-top: 8px;
}

.upload-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.upload-label {
  color: var(--ant-color-text);
  font-weight: 600;
}

.upload-file-row,
.upload-package {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
}

.upload-file-name,
.upload-package {
  min-width: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.upload-package-id {
  font-family: var(--font-monospace);
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

.upload-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}
</style>
