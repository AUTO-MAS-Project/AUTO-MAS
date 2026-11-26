<template>
  <a-row :gutter="24">
    <a-col :xs="24" :md="12">
      <a-form-item :label="t('core.edit.errorLogBundleDir')">
        <a-space-compact block>
          <a-input
            :value="run.LogBundlePath ?? ''"
            :placeholder="t('core.edit.errorLogBundleDirPlaceholder')"
            :aria-label="t('core.edit.errorLogBundleDir')"
            :disabled="!run.IfSaveLogBundle"
            readonly
            style="min-width: 0"
          />
          <a-button :disabled="!run.IfSaveLogBundle" @click="pickBundleDir">
            {{ t('core.edit.pickFolder') }}
          </a-button>
        </a-space-compact>
      </a-form-item>
    </a-col>
  </a-row>
  <a-row :gutter="24" style="margin-bottom: 12px">
    <a-col :xs="24" :md="12">
      <SwitchTile
        :checked="Boolean(run.IfSaveLogBundle)"
        :title="t('core.edit.errorLogBundle')"
        :description="t('core.edit.errorLogBundleHint')"
        @change="handleSwitchChange"
      />
    </a-col>
  </a-row>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { SwitchTile } from '@/components/ui'
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
    message.warning(t('core.edit.errorLogBundleNoPicker'))
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
