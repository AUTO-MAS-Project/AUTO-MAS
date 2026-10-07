<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { FileZipOutlined, PictureOutlined } from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'

import {
  useShareApi,
  type AppearanceCoverMode,
  type AppearanceUploadRecord,
} from '@/composables/useShareApi'
import type { OnlineAppearancePreview } from '@/types/appearance'
import {
  getCoverModes,
  isCoverReady,
  pickUploadTarget,
  type InheritCoverState,
} from '../myAppearance'
import type { MyAppearanceStore } from '../useMyAppearances'
import { formatAppearanceFileSize } from '../useOnlineAppearance'
import type { ShareAccount } from '../useShareAccount'
import ThemeStoreAccount from './ThemeStoreAccount.vue'

const props = defineProps<{
  open: boolean
  account: ShareAccount
  mine: MyAppearanceStore
  /** 外部指定的目标文件（「我的主题」或详情页的「上传新版本」）；指定后目标锁定。 */
  targetFileId?: number | null
}>()

const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'uploaded'): void
}>()

const DISPLAY_NAME_MAX = 60
const DESCRIPTION_MAX = 2000
const CHANGE_NOTE_MAX = 500
const COVER_MODE_LABELS: Record<AppearanceCoverMode, string> = {
  inherit: 'themeStore.upload.coverInherit',
  package: 'themeStore.upload.coverPackage',
  custom: 'themeStore.upload.coverCustom',
}

const { t } = useI18n()
const logger = window.electronAPI.getLogger('主题商店')
const { uploadAppearance, listAppearanceUploads, getInheritableAppearanceCover } = useShareApi()
const { authorized, refresh: refreshAccount } = props.account
const { items: mineItems, loading: mineLoading } = props.mine

const zipPath = ref('')
const inspecting = ref(false)
const inspectError = ref<string | null>(null)
const packageInfo = ref<{ appearance: OnlineAppearancePreview; fileSize: number } | null>(null)
const coverPath = ref<string | null>(null)
const coverPreviewUrl = ref<string | null>(null)
const coverMode = ref<AppearanceCoverMode>('package')
const uploads = ref<AppearanceUploadRecord[]>([])
const target = ref<'new' | 'update'>('new')
const selectedFileId = ref<number | null>(null)
// 用户自己改过目标后，后到的列表或记录不再改回默认
const targetTouched = ref(false)
// 锁定的目标在分享站上已经没了，解除锁定让用户改成新建
const lockLost = ref(false)
const submitting = ref(false)
const form = reactive({ displayName: '', description: '', changeNote: '' })

const fileName = (value: string): string => value.split(/[\\/]/).pop() ?? value

const lockedFileId = computed(() =>
  props.targetFileId != null && !lockLost.value ? props.targetFileId : null
)
const updating = computed(() => target.value === 'update')
const targetOptions = computed(() =>
  mineItems.value.map(item => ({ value: item.fileId, label: item.displayName || item.fileKey }))
)

// 分享站不带封面发新版本时沿用的那张（最近一个未被驳回且带封面的版本），按目标文件单独查
const inheritCover = ref<{
  fileId: number
  state: InheritCoverState
  dataUrl: string | null
} | null>(null)
let inheritRevision = 0
const inheritState = computed<InheritCoverState>(() => {
  if (!updating.value || selectedFileId.value === null) return 'none'
  if (inheritCover.value?.fileId !== selectedFileId.value) return 'loading'
  return inheritCover.value.state
})

const packagePreview = computed(() => packageInfo.value?.appearance.previewUrl)
const coverModes = computed(() =>
  getCoverModes({
    updating: updating.value,
    inheritCover: inheritState.value,
    packageHasPreview: Boolean(packagePreview.value),
  })
)
const coverImage = computed(() => {
  if (coverMode.value === 'inherit') {
    return inheritState.value === 'ready' ? (inheritCover.value?.dataUrl ?? null) : null
  }
  if (coverMode.value === 'package') return packagePreview.value ?? null
  return coverPreviewUrl.value
})
const coverReady = computed(() =>
  isCoverReady(coverMode.value, coverModes.value, {
    customPicked: Boolean(coverPath.value),
    inheritCover: inheritState.value,
  })
)

const loadInheritCover = async (fileId: number): Promise<void> => {
  const revision = ++inheritRevision
  inheritCover.value = { fileId, state: 'loading', dataUrl: null }
  const result = await getInheritableAppearanceCover(fileId)
  if (revision !== inheritRevision) return
  if (!result.ok && result.code !== 404) {
    logger.warn(`查询可沿用的外观封面失败: ${fileId}，${result.code} ${result.message}`)
  }
  inheritCover.value = result.ok
    ? { fileId, state: 'ready', dataUrl: result.data.dataUrl }
    : { fileId, state: 'none', dataUrl: null }
}
const canSubmit = computed(
  () =>
    authorized.value &&
    Boolean(packageInfo.value) &&
    coverReady.value &&
    (updating.value ? selectedFileId.value !== null : form.displayName.trim().length > 0) &&
    !submitting.value
)

const reset = (): void => {
  zipPath.value = ''
  inspecting.value = false
  inspectError.value = null
  packageInfo.value = null
  coverPath.value = null
  coverPreviewUrl.value = null
  coverMode.value = 'package'
  target.value = 'new'
  selectedFileId.value = null
  targetTouched.value = false
  lockLost.value = false
  inheritRevision += 1
  inheritCover.value = null
  form.displayName = ''
  form.description = ''
  form.changeNote = ''
}

const applyDefaultTarget = (): void => {
  if (targetTouched.value && lockedFileId.value === null) return
  const fileId = pickUploadTarget({
    lockedFileId: lockedFileId.value,
    appearanceId: packageInfo.value?.appearance.id ?? null,
    records: uploads.value,
    mine: mineItems.value,
  })
  target.value = fileId === null ? 'new' : 'update'
  selectedFileId.value = fileId
}

const loadTargets = async (): Promise<void> => {
  if (!authorized.value) {
    uploads.value = []
    return
  }
  const [records] = await Promise.all([listAppearanceUploads(), props.mine.ensureLoaded()])
  uploads.value = records
  applyDefaultTarget()
}

const changeTarget = (value: 'new' | 'update'): void => {
  targetTouched.value = true
  target.value = value
  if (value === 'update' && selectedFileId.value === null) {
    selectedFileId.value =
      pickUploadTarget({
        lockedFileId: null,
        appearanceId: packageInfo.value?.appearance.id ?? null,
        records: uploads.value,
        mine: mineItems.value,
      }) ??
      mineItems.value[0]?.fileId ??
      null
  }
}

const selectTarget = (value: SelectValue): void => {
  if (typeof value !== 'number') return
  targetTouched.value = true
  selectedFileId.value = value
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
    // 换了包就按新包重来：名称、描述取新包的，之前自选的封面作废
    form.displayName = result.appearance.name.slice(0, DISPLAY_NAME_MAX)
    form.description = (result.appearance.description ?? '').slice(0, DESCRIPTION_MAX)
    coverPath.value = null
    coverPreviewUrl.value = null
    applyDefaultTarget()
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
  // 主进程按上传时同样的规则先查一遍（≤8 MB、PNG / JPEG / WebP），不合格就不采用。
  const result = await window.electronAPI.inspectAppearanceCover?.(picked)
  if (!result?.success || !result.dataUrl) {
    message.error(result?.error || t('themeStore.upload.invalidCover'))
    return
  }
  coverPath.value = picked
  coverPreviewUrl.value = result.dataUrl
  coverMode.value = 'custom'
}

const usePackageCover = (): void => {
  coverPath.value = null
  coverPreviewUrl.value = null
  coverMode.value = 'package'
}

const close = (): void => {
  if (submitting.value) return
  emit('update:open', false)
}

const failureMessage = (result: { message: string; reason?: string }): string => {
  if (result.reason === 'conflict' && updating.value) return t('themeStore.upload.unchanged')
  if (result.reason === 'tooLarge') return t('themeStore.upload.tooLarge')
  return result.message || t('themeStore.upload.failed')
}

const submit = async (): Promise<void> => {
  if (!canSubmit.value || !packageInfo.value) return
  submitting.value = true
  try {
    const result = await uploadAppearance({
      zipPath: zipPath.value,
      displayName: updating.value ? '' : form.displayName.trim(),
      description: updating.value ? '' : form.description.trim(),
      changeNote: form.changeNote.trim(),
      fileId: updating.value ? selectedFileId.value : null,
      coverMode: coverMode.value,
      coverPath: coverMode.value === 'custom' ? coverPath.value : null,
    })
    if (!result.ok) {
      // 令牌过期时刷新一次登录状态，界面回到「登录分享站」
      if (result.code === 401) await refreshAccount()
      // 站上那个文件已经删了或不归这个账号：后端已删掉本机记录，这里改成按新外观上传
      if (updating.value && (result.code === 403 || result.code === 404)) {
        lockLost.value = true
        targetTouched.value = true
        target.value = 'new'
        selectedFileId.value = null
        void props.mine.load()
        message.warning(t('themeStore.upload.versionTargetGone'))
        return
      }
      message.error(failureMessage(result))
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

// 目标或包变了，封面来源回到默认（沿用 > 包内预览 > 自选）
watch([target, selectedFileId, packageInfo], () => {
  coverMode.value = coverModes.value[0] ?? 'custom'
})

// 可选来源变了（比如查完发现没有可沿用的封面），当前选的不在里面了才改回默认
watch(coverModes, modes => {
  if (!modes.includes(coverMode.value)) coverMode.value = modes[0] ?? 'custom'
})

// 目标一定下来就查分享站会沿用哪张封面
watch(
  [() => props.open, updating, selectedFileId],
  ([isOpen, isUpdating, fileId]) => {
    if (isOpen && isUpdating && fileId !== null && inheritCover.value?.fileId !== fileId) {
      void loadInheritCover(fileId)
    }
  },
  { immediate: true }
)

watch(
  () => props.open,
  isOpen => {
    if (!isOpen) return
    applyDefaultTarget()
    void loadTargets()
  },
  { immediate: true }
)

watch(authorized, isAuthorized => {
  if (isAuthorized && props.open) void loadTargets()
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
        <div class="upload-label">{{ t('themeStore.upload.target') }}</div>
        <a-radio-group
          :value="target"
          :disabled="submitting || lockedFileId !== null"
          @update:value="changeTarget"
        >
          <a-radio value="new">{{ t('themeStore.upload.targetNew') }}</a-radio>
          <a-radio value="update" :disabled="targetOptions.length === 0 && lockedFileId === null">
            {{ t('themeStore.upload.targetUpdate') }}
          </a-radio>
        </a-radio-group>
        <a-select
          v-if="updating"
          :value="selectedFileId ?? undefined"
          :options="targetOptions"
          :loading="mineLoading"
          :disabled="submitting || lockedFileId !== null"
          :placeholder="t('themeStore.upload.targetPlaceholder')"
          class="upload-target-select"
          @change="selectTarget"
        />
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
            <a-radio-group
              v-if="updating"
              v-model:value="coverMode"
              :disabled="submitting"
              class="upload-cover-modes"
            >
              <a-radio v-for="mode in coverModes" :key="mode" :value="mode">
                {{ t(COVER_MODE_LABELS[mode]) }}
              </a-radio>
            </a-radio-group>
            <span v-if="coverMode === 'custom' && coverPath" class="upload-file-name">
              {{ fileName(coverPath) }}
            </span>
            <template v-else-if="!updating">
              <span v-if="coverMode === 'package'" class="upload-hint">
                {{ t('themeStore.upload.coverFromPackage') }}
              </span>
              <span v-else class="upload-hint upload-hint-warning">
                {{ t('themeStore.upload.coverRequired') }}
              </span>
            </template>
            <span v-if="!updating || coverMode === 'custom'" class="upload-cover-buttons">
              <a-button size="small" :disabled="submitting" @click="pickCover">
                {{ t('themeStore.upload.pickCover') }}
              </a-button>
              <a-button
                v-if="!updating && coverMode === 'custom' && packagePreview"
                size="small"
                type="link"
                :disabled="submitting"
                @click="usePackageCover"
              >
                {{ t('themeStore.upload.usePackageCover') }}
              </a-button>
            </span>
            <span v-if="!updating || coverMode === 'custom'" class="upload-hint">
              {{ t('themeStore.upload.coverSpec') }}
            </span>
          </div>
        </div>
      </section>

      <a-form v-if="packageInfo" layout="vertical" class="upload-form">
        <a-form-item v-if="!updating" :label="t('themeStore.upload.name')" required>
          <a-input
            v-model:value="form.displayName"
            :maxlength="DISPLAY_NAME_MAX"
            show-count
            :disabled="submitting"
          />
        </a-form-item>
        <a-form-item v-if="!updating" :label="t('themeStore.upload.description')">
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

.upload-target-select {
  width: 100%;
}

.upload-cover-modes {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.upload-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}
</style>
