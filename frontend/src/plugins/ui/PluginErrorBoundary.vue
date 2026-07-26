<template>
  <div class="plugin-error-boundary">
    <slot v-if="!hasError" />
    <a-result v-else status="error" title="插件扩展加载失败">
      <template #sub-title>
        <div class="error-detail">
          <p>{{ errorMessage }}</p>
          <p v-if="extensionId" class="error-source">扩展 ID: {{ extensionId }}</p>
        </div>
      </template>
      <template #extra>
        <a-space>
          <a-button type="primary" @click="handleRetry">
            <template #icon>
              <ReloadOutlined />
            </template>
            重试
          </a-button>
          <a-button v-if="extensionId" @click="handleDisable">
            <template #icon>
              <StopOutlined />
            </template>
            本页停用
          </a-button>
          <a-button @click="handleCopyDiagnostics">
            <template #icon>
              <CopyOutlined />
            </template>
            复制诊断信息
          </a-button>
        </a-space>
      </template>
    </a-result>
  </div>
</template>

<script setup lang="ts">
import { onErrorCaptured, ref } from 'vue'
import { CopyOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

const props = withDefaults(
  defineProps<{
    /** 可选的扩展标识符，用于诊断 */
    extensionId?: string
    /** 插件名称 */
    pluginName?: string
  }>(),
  {
    extensionId: undefined,
    pluginName: undefined,
  }
)

const emit = defineEmits<{
  (e: 'error', payload: { extensionId?: string; message: string; error: unknown }): void
  (e: 'disable', extensionId?: string): void
  (e: 'retry'): void
}>()

const hasError = ref(false)
const errorMessage = ref('')
const lastError = ref<unknown>(null)

const buildDiagnostics = (): string => {
  const parts = [
    `时间: ${new Date().toISOString()}`,
    `扩展 ID: ${props.extensionId || '未指定'}`,
    `插件名称: ${props.pluginName || '未指定'}`,
    `错误信息: ${errorMessage.value}`,
    `错误详情: ${String(lastError.value ?? '无')}`,
  ]
  return parts.join('\n')
}

const handleRetry = () => {
  hasError.value = false
  errorMessage.value = ''
  lastError.value = null
  emit('retry')
}

const handleDisable = () => {
  emit('disable', props.extensionId)
}

const handleCopyDiagnostics = async () => {
  try {
    await navigator.clipboard.writeText(buildDiagnostics())
    message.success('诊断信息已复制到剪贴板')
  } catch {
    message.error('复制失败，请检查浏览器权限')
  }
}

onErrorCaptured((error: unknown, _instance, info: string) => {
  hasError.value = true
  errorMessage.value = error instanceof Error ? error.message : String(error)
  lastError.value = error

  emit('error', {
    extensionId: props.extensionId,
    message: errorMessage.value,
    error,
  })

  const logger = window.electronAPI?.getLogger?.('插件错误边界')
  logger?.error(
    `插件扩展错误: extensionId=${props.extensionId || '未知'}, ` +
      `plugin=${props.pluginName || '未知'}, info=${info}, error=${String(error)}`
  )

  // 阻止错误继续传播到父组件，实现宿主隔离
  return false
})
</script>

<style scoped>
.plugin-error-boundary {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.error-detail {
  text-align: left;
  max-width: 480px;
  margin: 0 auto;
}

.error-detail p {
  margin: 4px 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.error-source {
  font-family: monospace;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
