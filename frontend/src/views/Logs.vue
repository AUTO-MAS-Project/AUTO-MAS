<template>
  <div class="logs-page">
    <div class="page-header">
      <h2>系统日志</h2>
      <p>查看应用运行日志，支持搜索、过滤和导出功能</p>
    </div>
    
    <div class="logs-content">
      <LogViewer />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import LogViewer from '@/components/LogViewer.vue'
import { createComponentLogger } from '@/utils/logger'

const logger = createComponentLogger('LogsPage')

onMounted(() => {
  logger.info('进入日志查看页面')
})
</script>

<style scoped>
.logs-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0 0 8px 0;
  color: var(--ant-color-text);
  font-size: 24px;
  font-weight: 600;
}

.page-header p {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}

.logs-content {
  flex: 1;
  min-height: 0;
}
</style>