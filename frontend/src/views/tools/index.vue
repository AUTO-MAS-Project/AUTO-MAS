<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { OpenAPI } from '@/api'
import { useMcpApi } from '@/composables/useMcpApi'
import McpStartupSwitch from './components/McpStartupSwitch.vue'

const { t } = useI18n()
const { status, loading, retrying, error, refresh, retry, dispose } = useMcpApi()
const tick = ref(0)
const observedAt = ref(performance.now())
let timer: ReturnType<typeof setInterval> | undefined
const running = computed(() => status.value?.state === 'running')
const description = computed(() => {
  const snapshot = status.value
  if (!snapshot) return ''
  return t(`core.tools.mcp.${snapshot.state === 'running' ? snapshot.stage : snapshot.state}`)
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
    <div class="tools-header">
      <h1 class="page-title app-page-title">{{ t('core.tools.title') }}</h1>
    </div>
    <div class="tools-content">
      <a-tabs active-key="mcp" type="card" class="tools-tabs">
        <a-tab-pane key="mcp" :tab="t('core.tools.mcp.title')">
          <div class="tools-panel">
            <a-alert v-if="error" type="error" show-icon :message="error" class="tools-error">
              <template #action>
                <a-button size="small" :loading="loading" @click="refresh">{{
                  t('core.tools.mcp.refresh')
                }}</a-button>
              </template>
            </a-alert>
            <div v-if="!status" class="tools-initial-loading">
              <a-spin v-if="loading" />
              <a-empty v-else :description="t('core.tools.mcp.noStatus')" />
            </div>
            <template v-else>
              <McpStartupSwitch :status="status" />
              <div class="tools-service-header">
                <a-space>
                  <a-spin v-if="running" size="small" />
                  <a-tag :color="statusColor">{{ description }}</a-tag>
                </a-space>
                <a-button
                  v-if="status.state === 'failed'"
                  type="primary"
                  :loading="retrying"
                  :disabled="retrying || status.error === 'cleanup_failed'"
                  @click="retry"
                  >{{ t('core.tools.mcp.retry') }}</a-button
                >
              </div>
              <a-descriptions :column="1" size="small">
                <a-descriptions-item :label="t('core.tools.mcp.elapsed')">{{
                  elapsed
                }}</a-descriptions-item>
                <a-descriptions-item
                  v-if="status.state === 'ready'"
                  :label="t('core.tools.mcp.toolCount')"
                >
                  {{ status.toolCount }}
                </a-descriptions-item>
                <a-descriptions-item
                  v-if="status.state === 'ready'"
                  :label="t('core.tools.mcp.address')"
                >
                  <a-typography-text copyable>{{ address }}</a-typography-text>
                </a-descriptions-item>
              </a-descriptions>
              <a-alert
                v-if="status.error"
                type="error"
                show-icon
                :message="t(`core.tools.mcp.errors.${status.error}`)"
                :description="t('core.tools.mcp.seeLogs')"
              />
            </template>
          </div>
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<style scoped>
.tools-page {
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.tools-header {
  margin-bottom: 16px;
  padding: 0 4px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--app-page-title-color, var(--ant-color-text));
}

.tools-content {
  width: 100%;
  flex: 1;
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.tools-tabs {
  margin: 0;
  padding: 12px;
}

.tools-tabs :deep(.ant-tabs-nav) {
  margin: 0;
  padding: 0;
}

.tools-tabs :deep(.ant-tabs-content-holder) {
  overflow: visible;
}

.tools-tabs :deep(.ant-tabs-nav .ant-tabs-tab) {
  margin-right: 8px;
  background: transparent;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px 8px 0 0;
}

.tools-tabs :deep(.ant-tabs-nav .ant-tabs-tab-active) {
  background: var(--ant-color-bg-container);
  border-bottom-color: var(--ant-color-bg-container);
}

.tools-panel {
  width: 100%;
  padding: 24px;
}

.tools-service-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 24px;
}

.tools-error {
  margin-bottom: 16px;
}

.tools-initial-loading {
  min-height: 160px;
  display: grid;
  place-items: center;
}

@media (max-width: 860px) {
  .tools-tabs {
    padding: 8px;
  }

  .tools-panel {
    padding: 16px;
  }
}
</style>
