<script setup lang="ts">
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'
import type { AppearanceCoverMode } from '@/composables/useShareApi'
import type { OnlineAppearancePreview } from '@/types/appearance'
import type { AppearanceCategory } from '@/types/mascotPack'
import type { UploadPrecheckResult, UploadSubmissionMode } from '../uploadPrecheck'
import type { ShareAccount } from '../useShareAccount'
import AppearancePackagePicker from './AppearancePackagePicker.vue'
import AppearanceUploadCoverField from './AppearanceUploadCoverField.vue'
import ThemeStoreAccount from './ThemeStoreAccount.vue'
import UploadModeSelector from './UploadModeSelector.vue'
import UploadPrecheckPanel from './UploadPrecheckPanel.vue'

defineProps<{
  authorized: boolean
  account: ShareAccount
  category: AppearanceCategory
  allowCategoryChange: boolean
  submitting: boolean
  inspecting: boolean
  zipPath: string
  inspectError: string | null
  packageInfo: { appearance: OnlineAppearancePreview; fileSize: number } | null
  precheckResult: UploadPrecheckResult | null
  target: 'new' | 'update'
  lockedFileId: number | null
  selectedFileId: number | null
  targetOptions: Array<{ value: number; label: string }>
  mineLoading: boolean
  coverImage: string | null
  coverMode: AppearanceCoverMode
  coverModes: AppearanceCoverMode[]
  coverPath: string | null
  hasPackagePreview: boolean
  displayName: string
  description: string
  changeNote: string
  submissionMode: UploadSubmissionMode
  rememberMode: boolean
}>()

defineEmits<{
  'category-change': [category: AppearanceCategory]
  'pick-package': []
  'change-target': [value: 'new' | 'update']
  'select-target': [value: SelectValue]
  'update:coverMode': [value: AppearanceCoverMode]
  'pick-cover': []
  'use-package-cover': []
  'update:displayName': [value: string]
  'update:description': [value: string]
  'update:changeNote': [value: string]
  'update:submissionMode': [value: UploadSubmissionMode]
  'update:rememberMode': [value: boolean]
}>()

const DISPLAY_NAME_MAX = 60
const DESCRIPTION_MAX = 2000
const CHANGE_NOTE_MAX = 500
const { t } = useI18n()
</script>

<template>
  <div class="upload-body">
    <a-alert
      v-if="!authorized"
      type="info"
      show-icon
      :message="t('core.themeStore.upload.loginRequired')"
    >
      <template #description>
        <ThemeStoreAccount :account="account" class="upload-account" />
      </template>
    </a-alert>

    <section class="upload-section">
      <div class="upload-label">{{ t('core.themeStore.category') }}</div>
      <a-select
        :value="category"
        :disabled="!allowCategoryChange || submitting || inspecting || Boolean(zipPath)"
        :aria-label="t('core.themeStore.category')"
        style="width: 100%"
        @change="
          (value: SelectValue) => {
            if (value === 'theme' || value === 'mascot') $emit('category-change', value)
          }
        "
      >
        <a-select-option value="theme">{{ t('core.themeStore.categories.theme') }}</a-select-option>
        <a-select-option value="mascot">{{
          t('core.themeStore.categories.mascot')
        }}</a-select-option>
      </a-select>
    </section>

    <AppearancePackagePicker
      :inspecting="inspecting"
      :disabled="submitting"
      :zip-path="zipPath"
      :error="inspectError"
      :package-info="packageInfo"
      @pick="$emit('pick-package')"
    />

    <UploadPrecheckPanel v-if="precheckResult" :result="precheckResult" />

    <section v-if="packageInfo" class="upload-section">
      <div class="upload-label">{{ t('core.themeStore.upload.target') }}</div>
      <a-radio-group
        :value="target"
        :disabled="submitting || lockedFileId !== null"
        @update:value="$emit('change-target', $event)"
      >
        <a-radio value="new">{{ t('core.themeStore.upload.targetNew') }}</a-radio>
        <a-radio value="update" :disabled="targetOptions.length === 0 && lockedFileId === null">
          {{ t('core.themeStore.upload.targetUpdate') }}
        </a-radio>
      </a-radio-group>
      <a-select
        v-if="target === 'update'"
        :value="selectedFileId ?? undefined"
        :options="targetOptions"
        :loading="mineLoading"
        :disabled="submitting || lockedFileId !== null"
        :placeholder="t('core.themeStore.upload.targetPlaceholder')"
        class="upload-target-select"
        @change="$emit('select-target', $event)"
      />
    </section>

    <AppearanceUploadCoverField
      v-if="packageInfo"
      :updating="target === 'update'"
      :disabled="submitting"
      :cover-image="coverImage"
      :cover-alt="packageInfo.appearance.name"
      :cover-mode="coverMode"
      :cover-modes="coverModes"
      :cover-path="coverPath"
      :has-package-preview="hasPackagePreview"
      @update:cover-mode="$emit('update:coverMode', $event)"
      @pick-cover="$emit('pick-cover')"
      @use-package-cover="$emit('use-package-cover')"
    />

    <a-form v-if="packageInfo" layout="vertical" class="upload-form">
      <a-form-item v-if="target !== 'update'" :label="t('core.themeStore.upload.name')" required>
        <a-input
          :value="displayName"
          :maxlength="DISPLAY_NAME_MAX"
          show-count
          :disabled="submitting"
          @update:value="$emit('update:displayName', $event)"
        />
      </a-form-item>
      <a-form-item v-if="target !== 'update'" :label="t('core.themeStore.upload.description')">
        <a-textarea
          :value="description"
          :maxlength="DESCRIPTION_MAX"
          :auto-size="{ minRows: 2, maxRows: 5 }"
          :disabled="submitting"
          @update:value="$emit('update:description', $event)"
        />
      </a-form-item>
      <a-form-item :label="t('core.themeStore.upload.changeNote')">
        <a-input
          :value="changeNote"
          :maxlength="CHANGE_NOTE_MAX"
          :disabled="submitting"
          @update:value="$emit('update:changeNote', $event)"
        />
      </a-form-item>
    </a-form>

    <UploadModeSelector
      v-if="packageInfo"
      :mode="submissionMode"
      :remember-preference="rememberMode"
      :disabled="submitting || Boolean(precheckResult?.hasBlockingError)"
      @update:mode="$emit('update:submissionMode', $event)"
      @update:remember-preference="$emit('update:rememberMode', $event)"
    />
  </div>
</template>

<style scoped>
.upload-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.upload-target-select {
  width: 100%;
}

.upload-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}
</style>
