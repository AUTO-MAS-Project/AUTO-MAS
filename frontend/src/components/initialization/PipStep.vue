<template>
  <div class="step-panel">
    <h3>安装 pip 包管理器</h3>
    <div v-if="!pipInstalled" class="install-section">
      <p>pip 是 Python 的包管理工具，用于安装和管理 Python 包</p>
      
      <div class="pip-info">
        <a-alert 
          message="pip 安装信息" 
          description="将自动下载并安装 pip 包管理器，这是安装 Python 依赖包的必要工具。"
          type="info" 
          show-icon 
        />
      </div>
    </div>
    <div v-else class="already-installed">
      <a-result status="success" title="pip 已安装" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  pipInstalled: boolean
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

.pip-info {
  margin-top: 16px;
}

.already-installed {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>