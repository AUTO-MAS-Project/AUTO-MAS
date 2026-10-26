<template>
  <!-- display: contents 让这两个表单项继续作为父级网格的直接格子：开关占一格，目录占一整行 -->
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
      <a-switch :checked="run.IfSaveLogBundle" @change="handleSwitchChange" />
    </a-form-item>
    <a-form-item v-if="run.IfSaveLogBundle" class="bundle-item bundle-dir-item">
      <template #label>
        <span class="form-label">{{ t('edit.errorLogBundleDir') }}</span>
      </template>
      <a-space-compact block size="large">
        <a-input
          :value="run.LogBundlePath ?? ''"
          :placeholder="t('edit.errorLogBundleDirPlaceholder')"
          size="large"
          readonly
          class="bundle-path-input"
        />
        <a-button size="large" @click="pickBundleDir">
          {{ t('edit.pickFolder') }}
        </a-button>
      </a-space-compact>
      <div v-if="!run.LogBundlePath" class="bundle-warning">
        {{ t('edit.errorLogBundleDirPlaceholder') }}
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

/**
 * 开关状态只由用户决定，不拿「选没选目录」当前提：浏览器预览里目录选择器恒返回空、
 * 用户在弹窗里点取消也很正常，把这些当成拒绝打开会让开关看起来像坏了。打开时顺手
 * 弹一次选择器，选不选得上都不回滚开关，缺目录的后果由下面的红字提示说明。
 */
const handleSwitchChange = (checked: boolean) => {
  run.value.IfSaveLogBundle = checked
  emit('save', 'IfSaveLogBundle', checked)
  if (checked && !run.value.LogBundlePath) void pickBundleDir()
}
</script>

<style scoped>
.error-log-bundle-fields {
  display: contents;
}

.bundle-item {
  min-width: 0;
}

.bundle-dir-item {
  grid-column: 1 / -1;
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

.bundle-warning {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ant-color-error);
}
</style>
