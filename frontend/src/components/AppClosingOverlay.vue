<template>
  <Teleport to="body">
    <div v-if="visible" class="app-closing-overlay">
      <div class="closing-content">
        <div class="closing-spinner">
          <LoadingOutlined />
        </div>
        <div class="closing-text">正在关闭后端应用...</div>
        <div class="closing-subtitle">请稍候，应用即将退出</div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { LoadingOutlined } from '@ant-design/icons-vue'

defineProps<{
  visible: boolean
}>()
</script>

<style scoped>
.app-closing-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease-out;
}

.closing-content {
  text-align: center;
  color: white;
  padding: 32px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  min-width: 280px;
}

.closing-spinner {
  font-size: 32px;
  margin-bottom: 16px;
  color: #1890ff;
  animation: spin 1s linear infinite;
}

.closing-text {
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 8px;
  color: #ffffff;
}

.closing-subtitle {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
