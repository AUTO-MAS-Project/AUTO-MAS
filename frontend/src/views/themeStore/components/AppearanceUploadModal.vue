<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, EyeOutlined, UploadOutlined } from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'

import { AppModal } from '@/components/ui'
import {
  useShareApi,
  type AppearanceCoverMode,
  type AppearanceUploadRecord,
} from '@/composables/useShareApi'
import { useAppearanceTryOnStore } from '@/stores/appearanceTryOn'
import type { ImageDimensions, OnlineAppearancePreview } from '@/types/appearance'
import type { AppearanceCategory } from '@/types/mascotPack'
import { describePackageError } from '@/utils/resourcePackageError'
import {
  getCoverModes,
  isCoverReady,
  pickUploadTarget,
  type InheritCoverState,
} from '../myAppearance'
import {
  evaluateUploadPrecheck,
  readPreferredUploadMode,
  savePreferredUploadMode,
  type UploadSubmissionMode,
} from '../uploadPrecheck'
import type { MyAppearanceStore } from '../useMyAppearances'
import type { ShareAccount } from '../useShareAccount'
import AppearanceUploadEditStep from './AppearanceUploadEditStep.vue'
import UploadPreviewStep from './UploadPreviewStep.vue'

const props = defineProps<{
  open: boolean
  categoryKey?: AppearanceCategory
  allowCategoryChange?: boolean
  account: ShareAccount
  mine: MyAppearanceStore
  /** 外部指定的目标文件（「我的上传」或详情抽屉的「上传新版本」）；指定后目标锁定。 */
  targetFileId?: number | null
}>()

const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'uploaded'): void
  (event: 'category-change', category: AppearanceCategory): void
}>()

const DISPLAY_NAME_MAX = 60
const DESCRIPTION_MAX = 2000

const { t } = useI18n()
const logger = window.electronAPI.getLogger('主题商店')
const tryOnStore = useAppearanceTryOnStore()
const { uploadAppearance, listAppearanceUploads, getInheritableAppearanceCover } = useShareApi()
const { authorized, state: accountState, refresh: refreshAccount } = props.account
const { items: mineItems, loading: mineLoading } = props.mine

const step = ref<'edit' | 'preview'>('edit')
const submissionMode = ref<UploadSubmissionMode>(readPreferredUploadMode())
const rememberMode = ref(true)
const suspendedForTryOn = ref(false)

const zipPath = ref('')
const inspecting = ref(false)
const inspectError = ref<string | null>(null)
const packageInfo = ref<{ appearance: OnlineAppearancePreview; fileSize: number } | null>(null)
const coverPath = ref<string | null>(null)
const coverPreviewUrl = ref<string | null>(null)
const customCoverDimensions = ref<ImageDimensions | null>(null)
const coverMode = ref<AppearanceCoverMode>('package')
const uploads = ref<AppearanceUploadRecord[]>([])
const target = ref<'new' | 'update'>('new')
const selectedFileId = ref<number | null>(null)
const targetTouched = ref(false)
const lockLost = ref(false)
const submitting = ref(false)
const form = reactive({ displayName: '', description: '', changeNote: '' })

const resolvedCategory = computed<AppearanceCategory>(() => props.categoryKey ?? 'theme')
const lockedFileId = computed(() =>
  props.targetFileId != null && !lockLost.value ? props.targetFileId : null
)
const updating = computed(() => target.value === 'update')
const targetOptions = computed(() =>
  mineItems.value.map(item => ({ value: item.fileId, label: item.displayName || item.fileKey }))
)

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

// 机器可判定的预检在选包后自动运行；硬性缺失直接禁用上传，不随「直接上传」跳过。
const precheckResult = computed(() =>
  packageInfo.value
    ? evaluateUploadPrecheck({
        categoryKey: resolvedCategory.value,
        fileSize: packageInfo.value.fileSize,
        precheck: packageInfo.value.appearance.precheck,
        coverMode: coverMode.value,
        coverReady: coverReady.value,
        inheritCoverState: inheritState.value,
        customCoverDimensions: customCoverDimensions.value,
      })
    : null
)

const canProceed = computed(
  () =>
    authorized.value &&
    Boolean(packageInfo.value) &&
    coverReady.value &&
    !precheckResult.value?.hasBlockingError &&
    (updating.value ? selectedFileId.value !== null : form.displayName.trim().length > 0) &&
    !submitting.value
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

const reset = (): void => {
  if (suspendedForTryOn.value) return
  step.value = 'edit'
  zipPath.value = ''
  inspecting.value = false
  inspectError.value = null
  packageInfo.value = null
  coverPath.value = null
  coverPreviewUrl.value = null
  customCoverDimensions.value = null
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
  const [records] = await Promise.all([
    listAppearanceUploads(props.categoryKey),
    props.mine.ensureLoaded(),
  ])
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
    { name: t('core.themeStore.upload.packageFilter'), extensions: ['zip'] },
  ])
  const picked = paths[0]
  if (!picked) return
  inspecting.value = true
  inspectError.value = null
  try {
    const result = await window.electronAPI.inspectLocalAppearance?.(picked, props.categoryKey)
    if (!result?.success || !result.appearance) {
      packageInfo.value = null
      zipPath.value = ''
      inspectError.value = describePackageError(
        result,
        'core.themeStore.upload.invalidPackage',
        props.categoryKey
      )
      return
    }
    zipPath.value = picked
    packageInfo.value = { appearance: result.appearance, fileSize: result.fileSize ?? 0 }
    form.displayName = result.appearance.name.slice(0, DISPLAY_NAME_MAX)
    form.description = (result.appearance.description ?? '').slice(0, DESCRIPTION_MAX)
    coverPath.value = null
    coverPreviewUrl.value = null
    customCoverDimensions.value = null
    applyDefaultTarget()
  } catch (error) {
    logger.error(`读取外观包失败: ${error instanceof Error ? error.message : String(error)}`)
    inspectError.value = t('core.themeStore.upload.invalidPackage')
  } finally {
    inspecting.value = false
  }
}

const pickCover = async (): Promise<void> => {
  const paths = await window.electronAPI.selectFile([
    { name: t('core.themeStore.upload.coverFilter'), extensions: ['png', 'jpg', 'jpeg', 'webp'] },
  ])
  const picked = paths[0]
  if (!picked) return
  const result = await window.electronAPI.inspectAppearanceCover?.(picked)
  if (!result?.success || !result.dataUrl) {
    message.error(result?.error || t('core.themeStore.upload.invalidCover'))
    return
  }
  coverPath.value = picked
  coverPreviewUrl.value = result.dataUrl
  customCoverDimensions.value =
    result.width && result.height ? { width: result.width, height: result.height } : null
  coverMode.value = 'custom'
}

const usePackageCover = (): void => {
  coverPath.value = null
  coverPreviewUrl.value = null
  customCoverDimensions.value = null
  coverMode.value = 'package'
}

const close = (): void => {
  if (submitting.value) return
  suspendedForTryOn.value = false
  emit('update:open', false)
}

const failureMessage = (result: { message: string; reason?: string }): string => {
  if (result.reason === 'categoryMismatch') return t('core.themeStore.upload.categoryMismatch')
  if (result.reason === 'conflict' && updating.value) return t('core.themeStore.upload.unchanged')
  if (result.reason === 'tooLarge') return t('core.themeStore.upload.tooLarge')
  if (result.reason === 'pendingLimit') return t('core.themeStore.upload.pendingLimit')
  return result.message || t('core.themeStore.upload.failed')
}

const submit = async (): Promise<void> => {
  if (!canProceed.value || !packageInfo.value) return
  if (rememberMode.value) savePreferredUploadMode(submissionMode.value)
  submitting.value = true
  try {
    const result = await uploadAppearance({
      categoryKey: props.categoryKey,
      zipPath: zipPath.value,
      displayName: updating.value ? '' : form.displayName.trim(),
      description: updating.value ? '' : form.description.trim(),
      changeNote: form.changeNote.trim(),
      fileId: updating.value ? selectedFileId.value : null,
      coverMode: coverMode.value,
      coverPath: coverMode.value === 'custom' ? coverPath.value : null,
    })
    if (!result.ok) {
      if (result.code === 401) await refreshAccount()
      if (updating.value && (result.code === 403 || result.code === 404)) {
        lockLost.value = true
        targetTouched.value = true
        target.value = 'new'
        selectedFileId.value = null
        step.value = 'edit'
        void props.mine.load()
        message.warning(t('core.themeStore.upload.versionTargetGone'))
        return
      }
      message.error(failureMessage(result))
      return
    }
    message.success(
      result.data?.reviewStatus === 'approved'
        ? t('core.themeStore.upload.published')
        : t('core.themeStore.upload.submitted')
    )
    suspendedForTryOn.value = false
    emit('uploaded')
    emit('update:open', false)
  } finally {
    submitting.value = false
  }
}

const handlePrimaryAction = (): void => {
  if (!canProceed.value) return
  if (rememberMode.value) savePreferredUploadMode(submissionMode.value)
  if (step.value === 'edit' && submissionMode.value === 'preview') {
    step.value = 'preview'
    return
  }
  void submit()
}

const startUploadWindowTryOn = (): void => {
  const appearance = packageInfo.value?.appearance.tryOnAppearance
  if (!appearance) return
  suspendedForTryOn.value = true
  emit('update:open', false)
  tryOnStore.start({
    source: 'upload',
    title: form.displayName.trim() || appearance.name,
    versionNo: null,
    coverUrl: coverImage.value ?? undefined,
    hasBundledMascot: Boolean(packageInfo.value?.appearance.hasBundledMascot),
    appearance,
    onReturn: () => {
      suspendedForTryOn.value = false
      step.value = 'preview'
      emit('update:open', true)
    },
  })
}

watch([target, selectedFileId, packageInfo], () => {
  coverMode.value = coverModes.value[0] ?? 'custom'
})
watch(coverModes, modes => {
  if (!modes.includes(coverMode.value)) coverMode.value = modes[0] ?? 'custom'
})
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
  <AppModal
    :open="open"
    :size="step === 'preview' ? 'xl' : 'lg'"
    :title="
      step === 'preview'
        ? t('core.themeStore.upload.preview.modalTitle')
        : t('core.themeStore.upload.title')
    "
    :submitting="submitting"
    footer="custom"
    :after-close="reset"
    @update:open="value => !value && close()"
    @cancel="close"
  >
    <AppearanceUploadEditStep
      v-if="step === 'edit'"
      :authorized="authorized"
      :account="account"
      :category="resolvedCategory"
      :allow-category-change="allowCategoryChange ?? false"
      :submitting="submitting"
      :inspecting="inspecting"
      :zip-path="zipPath"
      :inspect-error="inspectError"
      :package-info="packageInfo"
      :precheck-result="precheckResult"
      :target="target"
      :locked-file-id="lockedFileId"
      :selected-file-id="selectedFileId"
      :target-options="targetOptions"
      :mine-loading="mineLoading"
      :cover-image="coverImage"
      :cover-mode="coverMode"
      :cover-modes="coverModes"
      :cover-path="coverPath"
      :has-package-preview="Boolean(packagePreview)"
      :display-name="form.displayName"
      :description="form.description"
      :change-note="form.changeNote"
      :submission-mode="submissionMode"
      :remember-mode="rememberMode"
      @category-change="emit('category-change', $event)"
      @pick-package="pickPackage"
      @change-target="changeTarget"
      @select-target="selectTarget"
      @update:cover-mode="coverMode = $event"
      @pick-cover="pickCover"
      @use-package-cover="usePackageCover"
      @update:display-name="form.displayName = $event"
      @update:description="form.description = $event"
      @update:change-note="form.changeNote = $event"
      @update:submission-mode="submissionMode = $event"
      @update:remember-mode="rememberMode = $event"
    />

    <UploadPreviewStep
      v-else-if="packageInfo && precheckResult"
      :category-key="resolvedCategory"
      :display-name="form.displayName"
      :description="form.description"
      :change-note="form.changeNote"
      :author-name="accountState.displayName || accountState.username"
      :updating="updating"
      :cover-image="coverImage"
      :file-size="packageInfo.fileSize"
      :appearance="packageInfo.appearance"
      :precheck="precheckResult"
      @try-on-window="startUploadWindowTryOn"
    />

    <template #footer>
      <div class="upload-footer">
        <a-button v-if="step === 'preview'" :disabled="submitting" @click="step = 'edit'">
          <template #icon><ArrowLeftOutlined /></template>
          {{ t('core.themeStore.upload.preview.backToEdit') }}
        </a-button>
        <span v-else />
        <div class="upload-footer-right">
          <a-button :disabled="submitting" @click="close">{{ t('core.common.cancel') }}</a-button>
          <a-button
            type="primary"
            :loading="submitting"
            :disabled="!canProceed"
            @click="handlePrimaryAction"
          >
            <template #icon>
              <EyeOutlined v-if="step === 'edit' && submissionMode === 'preview'" />
              <UploadOutlined v-else />
            </template>
            {{
              step === 'edit' && submissionMode === 'preview'
                ? t('core.themeStore.upload.mode.nextPreview')
                : step === 'preview'
                  ? t('core.themeStore.upload.preview.confirmSubmit')
                  : t('core.themeStore.upload.mode.directSubmit')
            }}
          </a-button>
        </div>
      </div>
    </template>
  </AppModal>
</template>

<style scoped>
.upload-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.upload-footer-right {
  display: flex;
  gap: 8px;
}
</style>
