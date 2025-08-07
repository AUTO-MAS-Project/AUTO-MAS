<template>
  <div class="step-panel">
    <h3>Git 版本控制工具</h3>
    <div v-if="!gitInstalled" class="install-section">
      <p>需要安装 Git 工具来获取源代码</p>
      <div class="git-info">
        <a-alert 
          message="Git 工具信息" 
          description="将安装便携版 Git 工具，包含完整的版本控制功能，无需系统安装。"
          type="info" 
          show-icon 
        />
      </div>
    </div>
    <div v-else class="already-installed">
      <a-result status="success" title="Git 工具已安装" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  gitInstalled: boolean
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

.git-info {
  margin-top: 16px;
}

.already-installed {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>