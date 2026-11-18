<template>
  <div class="global-options-panel">
    <div class="global-options-header">
      <div class="global-options-title">{{ t('core.edit.maafwGlobalOptions') }}</div>
      <div class="global-options-hint">{{ t('core.edit.maafwGlobalOptionsHint') }}</div>
    </div>
    <MaaFWTaskOptionEditor
      :option-names="previewData.globalOption"
      :options="previewData.options"
      :task-options="globalOptions"
      :controller-name="effectiveControllerName"
      :resource-name="effectiveResourceName"
      :base-path="previewData.path"
      :disabled="disabled"
      @update="payload => emit('update', payload)"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import MaaFWTaskOptionEditor from '../MaaFWTaskOptionEditor.vue'
import type { MaaFWInterfacePreviewData, MaaFWTaskOptionValue } from '@/types/script'

/**
 * 任务队列右栏：选中左栏置顶的「全局选项」时显示。每个用户只设一次，队列里的所有任务共用；
 * 任务配置里不再列它们。模板根上不放注释，父级要在它上面挂 v-show。
 */
defineProps<{
  previewData: MaaFWInterfacePreviewData
  /** 快照里的全局选项值（taskSnapshot.globalOptions） */
  globalOptions: Record<string, MaaFWTaskOptionValue>
  effectiveControllerName: string
  effectiveResourceName: string
  disabled: boolean
}>()

const emit = defineEmits<{
  update: [payload: { optionName: string; value: MaaFWTaskOptionValue }]
}>()

const { t } = useI18n()
</script>

<style scoped>
/* 框线、内距与任务配置面板（MaaFWTaskConfigPanel）一致，切换时右栏不跳 */
.global-options-panel {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.global-options-header {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.global-options-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.global-options-hint {
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}
</style>
