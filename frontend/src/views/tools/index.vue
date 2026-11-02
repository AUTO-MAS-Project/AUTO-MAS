<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { OpenAPI } from '@/api'
import { useMcpApi } from '@/composables/useMcpApi'

const { t } = useI18n()
const { status, loading, retrying, error, refresh, retry, dispose } = useMcpApi()
const tick = ref(0)
const observedAt = ref(performance.now())
let timer: ReturnType<typeof setInterval> | undefined
const running = computed(() => status.value?.state === 'running')
const description = computed(() => {
  const snapshot = status.value
  if (!snapshot) return ''
  return t(`tools.mcp.${snapshot.state === 'running' ? snapshot.stage : snapshot.state}`)
})
const elapsed = computed(() => {
  const snapshot = status.value
  if (!snapshot) return '—'
  const extra = running.value ? Math.max(0, tick.value - observedAt.value) : 0
  return `${((snapshot.elapsedMs + extra) / 1000).toFixed(1)} s`
})
const address = computed(() => `${OpenAPI.BASE.replace(/\/+$/, '')}/mcp`)
const statusColor = computed(() => {
  if (status.value?.state === 'ready') return 'success'
  if (status.value?.state === 'failed') return 'error'
  return running.value ? 'processing' : 'default'
})

// 用浏览器单调时钟累计收到快照后的时长，不受两端墙钟偏差影响。
watch(status, () => {
  observedAt.value = performance.now()
  tick.value = observedAt.value
})
onMounted(() => {
  void refresh()
  timer = setInterval(() => {
    tick.value = performance.now()
  }, 250)
})
onUnmounted(() => {
  clearInterval(timer)
  dispose()
})
</script>

<template>
  <div class="tools-page">
    <h1>{{ t('tools.title') }}</h1>
    <a-alert v-if="error" type="error" show-icon :message="error" class="tools-error">
      <template #action>
        <a-button size="small" :loading="loading" @click="refresh">{{
          t('tools.mcp.refresh')
        }}</a-button>
      </template>
    </a-alert>
    <a-card :title="t('tools.mcp.title')">
      <template #extra>
        <a-button
          v-if="status?.state === 'failed'"
          type="primary"
          :loading="retrying"
          :disabled="retrying || status.error === 'cleanup_failed'"
          @click="retry"
          >{{ t('tools.mcp.retry') }}</a-button
        >
      </template>
      <div v-if="!status" class="tools-initial-loading">
        <a-spin v-if="loading" />
        <a-empty v-else :description="t('tools.mcp.noStatus')" />
      </div>
      <template v-else>
        <a-space class="tools-status">
          <a-spin v-if="running" size="small" />
          <a-tag :color="statusColor">{{ description }}</a-tag>
        </a-space>
        <a-descriptions :column="1" size="small">
          <a-descriptions-item :label="t('tools.mcp.enabled')">
            {{ t(status.enabled ? 'tools.mcp.yes' : 'tools.mcp.no') }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('tools.mcp.elapsed')">{{ elapsed }}</a-descriptions-item>
          <a-descriptions-item v-if="status.state === 'ready'" :label="t('tools.mcp.toolCount')">
            {{ status.toolCount }}
          </a-descriptions-item>
          <a-descriptions-item v-if="status.state === 'ready'" :label="t('tools.mcp.address')">
            <a-typography-text copyable>{{ address }}</a-typography-text>
          </a-descriptions-item>
        </a-descriptions>
        <a-alert
          v-if="status.error"
          type="error"
          show-icon
          :message="t(`tools.mcp.errors.${status.error}`)"
          :description="t('tools.mcp.seeLogs')"
        />
      </template>
    </a-card>
  </div>
</template>

<style scoped>
.tools-page {
  padding: 24px;
}
.tools-page h1 {
  margin: 0 0 24px;
  font-size: 24px;
  color: var(--ant-color-text);
}
.tools-status,
.tools-error {
  margin-bottom: 16px;
}
.tools-initial-loading {
  min-height: 160px;
  display: grid;
  place-items: center;
}
</style>
