<template>
  <div class="step-panel">
    <h3>依赖安装</h3>
    <div class="install-section">
      <!-- 环境检查 -->
      <div v-if="checking" class="check-status">
        <p>正在检查依赖状态...</p>
      </div>

      <!-- 依赖状态 -->
      <div v-else-if="!installing" class="dependency-status">
        <a-alert
          :type="needsInstall ? 'warning' : 'success'"
          :message="needsInstall ? '需要安装依赖' : '依赖已是最新'"
          :description="
            needsInstall
              ? 'requirements.txt 已更新，需要重新安装依赖'
              : '依赖包已是最新版本，无需重新安装'
          "
          show-icon
        />
      </div>

      <!-- 安装进度 -->
      <div v-if="installing" class="install-progress">
        <div class="progress-info">
          <span>{{ installMessage }}</span>
        </div>
        <a-progress :percent="installProgress" :status="progressStatus" />
        <div v-if="currentMirror" class="current-mirror">
          <span>当前使用: {{ currentMirror }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  checking: boolean
  needsInstall: boolean
  installing: boolean
  completed: boolean
  installProgress: number
  installMessage: string
  currentMirror?: string
  progressStatus?: 'normal' | 'exception' | 'success'
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

.check-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px 0;
}

.dependency-status {
  padding: 12px 0;
}

.install-progress {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px;
  background: var(--ant-color-bg-container);
  border-radius: 8px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: var(--ant-color-text);
}

.current-mirror {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  text-align: center;
}

.completed-status {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>
