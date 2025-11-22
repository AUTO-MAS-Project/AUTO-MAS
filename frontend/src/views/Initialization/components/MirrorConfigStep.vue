<template>
  <div class="step-panel">
    <h3>镜像源配置</h3>
    <div class="install-section">
      <div class="mirror-status">
        <a-spin v-if="loading" size="large" tip="正在从云端获取镜像源配置..." />
        <a-result
          v-else-if="success"
          status="success"
          title="镜像源配置加载成功"
          :sub-title="`已加载 ${mirrorCount} 个镜像源配置`"
        />
        <a-result
          v-else
          status="warning"
          title="使用本地默认配置"
          sub-title="云端配置加载失败，将使用本地默认镜像源"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  loading: boolean
  success: boolean
  mirrorCount: number
}>()
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

.install-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.install-section p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.mirror-status {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>
