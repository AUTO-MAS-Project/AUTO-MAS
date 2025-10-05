<template>
  <div class="logs-container">
    <div class="logs-header">
      <div class="header-content">
        <div class="title-section">
          <h1>日志查看</h1>
          <p class="logs-description">查看和管理应用程序日志</p>
        </div>
        <a-button size="large" @click="goBack">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回设置
        </a-button>
      </div>
    </div>

    <LogViewer />
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import LogViewer from '@/components/LogViewer.vue'

const router = useRouter()

const goBack = () => {
  router.push('/settings')
}
</script>

<style scoped>
.logs-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.logs-header {
  margin-bottom: 24px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.title-section {
  flex: 1;
}

.logs-header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.logs-description {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  line-height: 1.5;
}
</style>
