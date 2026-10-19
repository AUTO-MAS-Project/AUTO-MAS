<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  DeleteOutlined,
  PictureOutlined,
  QuestionCircleOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useTheme } from '@/composables/useTheme'
import { CUSTOM_BACKGROUND_MAX_BYTES, hasCustomBackgroundExtension } from '@/utils/customBackground'
import { createCustomSurfaceOpacityControl } from './customSurfaceOpacityControl'

const { t } = useI18n()
const {
  activeAppearance,
  customBackgroundPath,
  customBackgroundUrl,
  customBackgroundLoadFailed,
  customSurfaceOpacity,
  setCustomBackground,
  clearCustomBackground,
  retryCustomBackground,
  previewCustomSurfaceOpacity,
  setCustomSurfaceOpacity,
} = useTheme()

const importing = ref(false)
const clearing = ref(false)
const retrying = ref(false)
const hasAppearanceBackground = computed(() => Boolean(activeAppearance.value?.backgroundUrl))
const {
  displayedValue: displayedSurfaceOpacity,
  startPreview: handleOpacityChange,
  commitValue: handleOpacityAfterChange,
} = createCustomSurfaceOpacityControl({
  readValue: () => customSurfaceOpacity.value,
  previewValue: previewCustomSurfaceOpacity,
  saveValue: setCustomSurfaceOpacity,
  onSaveError: () => message.error(t('setting.basic.customSurfaceOpacitySaveFailed')),
})

const customBackgroundFileName = computed(() => {
  const path = typeof customBackgroundPath.value === 'string' ? customBackgroundPath.value : ''
  return path.split(/[\\/]/).pop() ?? path
})

const handleImport = async (): Promise<void> => {
  importing.value = true
  try {
    const paths = await window.electronAPI.selectFile([
      {
        name: t('setting.basic.customBackgroundFileTypeName'),
        extensions: ['bmp', 'gif', 'jpg', 'jpeg', 'png', 'webp'],
      },
    ])
    if (paths.length === 0) return

    const filePath = paths[0]
    if (!hasCustomBackgroundExtension(filePath)) {
      message.error(t('setting.basic.customBackgroundUnsupported'))
      return
    }

    // 上限交给主进程把关，超限时不把整个文件读进渲染进程。
    const { base64, size } = await window.electronAPI.readFileBase64(
      filePath,
      CUSTOM_BACKGROUND_MAX_BYTES
    )
    if (size > CUSTOM_BACKGROUND_MAX_BYTES) {
      message.error(t('setting.basic.customBackgroundTooLarge'))
      return
    }
    if (!base64) {
      message.error(t('setting.basic.customBackgroundReadFailed'))
      return
    }

    await setCustomBackground(filePath, base64)
    message.success(t('setting.basic.customBackgroundImported'))
  } catch (error) {
    message.error(
      error instanceof Error && error.message === '自定义背景尺寸过大或图片无效'
        ? t('setting.basic.customBackgroundDimensionsUnsupported')
        : t('setting.basic.customBackgroundImportFailed')
    )
  } finally {
    importing.value = false
  }
}

const handleClear = async (): Promise<void> => {
  clearing.value = true
  try {
    await clearCustomBackground()
    message.success(t('setting.basic.customBackgroundRemoved'))
  } catch {
    message.error(t('setting.basic.customBackgroundRemoveFailed'))
  } finally {
    clearing.value = false
  }
}

const handleRetry = async (): Promise<void> => {
  retrying.value = true
  try {
    await retryCustomBackground()
  } finally {
    retrying.value = false
  }
}
</script>

<template>
  <div class="form-section custom-background-settings">
    <div class="section-header">
      <h3>{{ t('setting.basic.customBackgroundSection') }}</h3>
    </div>
    <a-alert
      v-if="hasAppearanceBackground"
      class="package-background-alert"
      type="info"
      :message="t('setting.basic.customBackgroundPackageActive')"
      show-icon
    />
    <a-row :gutter="24">
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.basic.customBackground') }}</span>
            <a-tooltip :title="t('setting.basic.customBackgroundTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <div class="background-controls">
            <a-button
              :loading="importing"
              :disabled="importing || clearing"
              @click="handleImport"
            >
              <template #icon><UploadOutlined /></template>
              {{ t('setting.basic.customBackgroundSelect') }}
            </a-button>
            <a-button
              v-if="customBackgroundPath"
              danger
              :loading="clearing"
              :disabled="importing || clearing"
              :aria-label="t('setting.basic.customBackgroundClear')"
              @click="handleClear"
            >
              <template #icon><DeleteOutlined /></template>
              {{ t('setting.basic.customBackgroundClear') }}
            </a-button>
          </div>
          <div class="background-state">
            <PictureOutlined class="background-state-icon" />
            <span v-if="customBackgroundPath" :title="customBackgroundPath">
              {{ customBackgroundFileName }}
            </span>
            <span v-else>{{ t('setting.basic.customBackgroundEmpty') }}</span>
          </div>
          <div v-if="customBackgroundLoadFailed" class="background-load-error">
            <span>{{ t('setting.basic.customBackgroundLoadFailed') }}</span>
            <a-button size="small" :loading="retrying" @click="handleRetry">
              {{ t('setting.basic.customBackgroundRetry') }}
            </a-button>
          </div>
        </div>
      </a-col>
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.basic.customSurfaceOpacity') }}</span>
            <a-tooltip :title="t('setting.basic.customSurfaceOpacityTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <div class="opacity-controls">
            <a-slider
              style="flex: 1; min-width: 0"
              :value="displayedSurfaceOpacity"
              :min="0.1"
              :max="1"
              :step="0.05"
              :disabled="!customBackgroundUrl || hasAppearanceBackground"
              :aria-label="t('setting.basic.customSurfaceOpacity')"
              @change="handleOpacityChange"
              @afterChange="handleOpacityAfterChange"
            />
            <span class="opacity-percent"> {{ Math.round(displayedSurfaceOpacity * 100) }}% </span>
          </div>
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.package-background-alert {
  margin-bottom: 16px;
}

.background-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.background-state {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin-top: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.background-state span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.background-state-icon {
  flex: 0 0 auto;
}

.background-load-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  color: var(--ant-color-error);
  font-size: 12px;
}

.opacity-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.opacity-percent {
  flex: 0 0 auto;
  min-width: 44px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
