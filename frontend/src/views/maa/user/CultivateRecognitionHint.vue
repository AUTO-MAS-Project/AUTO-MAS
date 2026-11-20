<template>
  <!-- 识别口径一行摘要，完整说明收进行尾 ?（对齐 PipelineRow 的 row-help） -->
  <div class="cultivate-hint cultivate-hint-inline">
    {{ t('core.maaCopilot.recognitionHintShort') }}
    <a-tooltip
      :title="t('plugins.maa_adapter.edit.maaCultivateRecognitionHint')"
      :trigger="['hover', 'focus']"
    >
      <button
        type="button"
        class="hint-help"
        :aria-label="t('plugins.maa_adapter.edit.maaCultivateRecognitionHint')"
      >
        <QuestionCircleOutlined aria-hidden="true" />
      </button>
    </a-tooltip>
  </div>
  <div v-if="!sklandBound" class="cultivate-hint cultivate-hint-inline">
    {{ t('plugins.maa_adapter.edit.maaCultivateSklandUnboundHint') }}
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

defineProps<{ sklandBound: boolean }>()
const { t } = useI18n()
</script>

<style scoped>
.cultivate-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.cultivate-hint-inline {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 0 6px;
}

/* 行尾 ? 说明按钮（可聚焦，对齐 PipelineRow 的 row-help 口径） */
.hint-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  cursor: help;
}

.hint-help:hover {
  color: var(--ant-color-primary);
}

.hint-help:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 1px;
}
</style>
