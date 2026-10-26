<template>
  <div class="error-log-bundle-fields">
    <a-form-item class="bundle-item">
      <template #label>
        <span class="form-label">
          {{ t('edit.errorLogBundle') }}
          <a-tooltip :title="t('edit.errorLogBundleHint')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </span>
      </template>
      <div class="bundle-controls">
        <a-switch :checked="run.IfSaveLogBundle" @change="handleSwitchChange" />
        <a-space-compact block size="large" class="bundle-directory">
          <a-input
            :value="run.LogBundlePath ?? ''"
            :placeholder="t('edit.errorLogBundleDirPlaceholder')"
            :aria-label="t('edit.errorLogBundleDir')"
            :disabled="!run.IfSaveLogBundle"
            size="large"
            readonly
            class="bundle-path-input"
          />
          <a-button size="large" :disabled="!run.IfSaveLogBundle" @click="pickBundleDir">
            {{ t('edit.pickFolder') }}
          </a-button>
        </a-space-compact>
      </div>
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaEndScriptConfig } from '@/types/script'

type RunConfig = MaaEndScriptConfig['Run']
const run = defineModel<RunConfig>('run', { required: true })
const emit = defineEmits<{
  save: [key: keyof RunConfig, value: RunConfig[keyof RunConfig]]
}>()
const { t } = useI18n()

/** 目录只能通过桌面端目录选择器指定；取消或环境不支持时返回 null。 */
const pickBundleDir = async () => {
  if (!window.electronAPI?.selectFolder) {
    message.warning(t('edit.errorLogBundleNoPicker'))
    return
  }
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  run.value.LogBundlePath = picked
  emit('save', 'LogBundlePath', picked)
}

/** 留空使用后端默认目录，开启时无需先选择文件夹。 */
const handleSwitchChange = (checked: boolean) => {
  run.value.IfSaveLogBundle = checked
  emit('save', 'IfSaveLogBundle', checked)
}
</script>

<style scoped>
.error-log-bundle-fields {
  grid-column: 1 / -1;
  min-width: 0;
}

.bundle-item {
  min-width: 0;
}

.bundle-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

.bundle-directory {
  flex: 1;
  min-width: 0;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.bundle-path-input {
  min-width: 0;
}
</style>
