<template>
  <div class="logs-container">
    <div class="logs-header">
      <div class="header-content">
        <div class="title-section">
          <h1>日志查看</h1>
          <p class="logs-description">查看和管理应用程序日志</p>
        </div>
        <a-button @click="goBack" size="large">
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
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import LogViewer from '@/components/LogViewer.vue'
import { useTheme } from '@/composables/useTheme'

const router = useRouter()
const { isDark } = useTheme()

const textColor = computed(() =>
  isDark.value ? 'rgba(255, 255, 255, 0.88)' : 'rgba(0, 0, 0, 0.88)'
)
const textSecondaryColor = computed(() =>
  isDark.value ? 'rgba(255, 255, 255, 0.65)' : 'rgba(0, 0, 0, 0.65)'
)

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
  color: v-bind(textColor);
}

.logs-description {
  margin: 0;
  color: v-bind(textSecondaryColor);
  font-size: 14px;
  line-height: 1.5;
}
</style>