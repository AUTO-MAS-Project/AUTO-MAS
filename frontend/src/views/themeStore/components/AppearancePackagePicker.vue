<script setup lang="ts">
import { FileZipOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { OnlineAppearancePreview } from '@/types/appearance'
import { formatAppearanceFileSize } from '../useOnlineAppearance'

defineProps<{
  inspecting: boolean
  disabled: boolean
  zipPath: string
  error: string | null
  packageInfo: { appearance: OnlineAppearancePreview; fileSize: number } | null
}>()

defineEmits<{ pick: [] }>()
const { t } = useI18n()
</script>

<template>
  <section class="package-picker">
    <div class="package-label">{{ t('core.themeStore.upload.package') }}</div>
    <div class="package-row">
      <a-button :loading="inspecting" :disabled="disabled" @click="$emit('pick')">
        <template #icon><FileZipOutlined /></template>
        {{ zipPath ? t('core.themeStore.upload.repick') : t('core.themeStore.upload.pick') }}
      </a-button>
      <span v-if="zipPath" class="package-file">
        {{ zipPath.split(/[\\/]/).pop() }} ·
        {{ formatAppearanceFileSize(packageInfo?.fileSize ?? 0) }}
      </span>
    </div>
    <a-alert v-if="error" type="error" show-icon :message="error" />
    <div v-if="packageInfo" class="package-info package-row">
      <span class="package-id">ID {{ packageInfo.appearance.id }}</span>
      <span v-if="packageInfo.appearance.mode">
        {{
          packageInfo.appearance.mode === 'dark'
            ? t('core.setting.themeMode.dark')
            : t('core.setting.themeMode.light')
        }}
      </span>
    </div>
  </section>
</template>

<style scoped>
.package-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.package-label {
  color: var(--ant-color-text);
  font-weight: 600;
}

.package-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
}

.package-file,
.package-info {
  min-width: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.package-id {
  font-family: var(--font-monospace);
}
</style>
