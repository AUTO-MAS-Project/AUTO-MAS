<template>
  <div v-if="hasContent" class="diagnostics-details">
    <a-collapse ghost size="small">
      <a-collapse-panel key="diagnostics" :header="t('common.diagnostics')">
        <div class="diagnostics-body">
          <pre v-if="detail" class="diagnostics-text">{{ detail }}</pre>
          <pre v-if="contextText" class="diagnostics-text">{{ contextText }}</pre>
          <a-button size="small" @click="copyDiagnostics">{{
            t('common.copyDiagnostics')
          }}</a-button>
        </div>
      </a-collapse-panel>
    </a-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'

defineOptions({ name: 'DiagnosticsDetails' })

const props = defineProps<{
  detail?: string
  context?: Record<string, unknown>
}>()

const { t } = useI18n()

const contextText = computed(() => (props.context ? JSON.stringify(props.context, null, 2) : ''))
const hasContent = computed(() => Boolean(props.detail || contextText.value))

// 技术原文原样复制，方便用户反馈时贴给支持。
async function copyDiagnostics() {
  const parts = [props.detail, contextText.value].filter((part): part is string => Boolean(part))
  if (parts.length === 0) return

  try {
    await navigator.clipboard.writeText(parts.join('\n'))
    message.success(t('common.copied'))
  } catch (error) {
    // 复制失败时正文仍在页面上，用户可以直接选中。
    console.error('[diagnostics] 复制失败', error)
    message.error(t('common.copyFailed'))
  }
}
</script>

<style scoped>
.diagnostics-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}

.diagnostics-text {
  max-width: 100%;
  max-height: 200px;
  margin: 0;
  padding: 8px;
  overflow: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: var(--ant-color-fill-quaternary, transparent);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
