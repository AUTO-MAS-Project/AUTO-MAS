<template>
  <div class="step-panel">
    <h3>启动后端服务</h3>
    <div class="service-status">
      <a-spin :spinning="startingService">
        <div class="status-info">
          <p>{{ serviceStatus }}</p>
          <a-progress v-if="showServiceProgress" :percent="serviceProgress" />
        </div>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const startingService = ref(false)
const showServiceProgress = ref(false)
const serviceProgress = ref(0)
const serviceStatus = ref('准备启动后端服务...')

defineExpose({
  startingService,
  showServiceProgress,
  serviceProgress,
  serviceStatus,
})
</script>

<style scoped>
.step-panel {
  padding: 20px;
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}

.step-panel h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 20px;
}

.service-status {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.status-info {
  text-align: center;
  width: 100%;
}

.status-info p {
  font-size: 16px;
  color: var(--ant-color-text);
  margin-bottom: 16px;
}
</style>