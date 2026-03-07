<template>
  <Teleport to="body">
    <div v-if="visible" class="backend-startup-overlay">
      <div class="startup-content">
        <div class="startup-spinner">
          <LoadingOutlined />
        </div>
        <div class="startup-text">正在启动后端服务...</div>
        <div class="startup-subtitle">请稍候，马上进入主界面</div>
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
.backend-startup-overlay {
  position: fixed;
  top: 32px;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  z-index: 9998;
  animation: fadeIn 0.2s ease-out;
}

.startup-content {
  min-width: 300px;
  padding: 28px 32px;
  text-align: center;
  color: #ffffff;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 10px 36px rgba(0, 0, 0, 0.32);
}

.startup-spinner {
  margin-bottom: 16px;
  font-size: 34px;
  color: #1890ff;
  animation: spin 1s linear infinite;
}

.startup-text {
  margin-bottom: 8px;
  font-size: 18px;
  font-weight: 500;
}

.startup-subtitle {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.72);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.96);
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
