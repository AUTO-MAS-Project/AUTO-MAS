<template>
  <div class="step-panel">
    <h3>{{ t('init.repository.title') }}</h3>
    <div class="install-section">
      <!-- 环境检查 -->
      <div v-if="checking" class="check-status">
        <p>{{ t('init.repository.checking') }}</p>
      </div>

      <!-- 仓库状态 -->
      <div v-else-if="!pulling" class="repo-status">
        <a-alert
          :type="repoExists ? 'info' : 'warning'"
          :message="repoExists ? t('init.repository.exists') : t('init.repository.missing')"
          :description="
            repoExists ? t('init.repository.willUpdate') : t('init.repository.willClone')
          "
          show-icon
        />
      </div>

      <!-- 拉取进度 -->
      <div v-if="pulling" class="pull-progress">
        <div class="progress-info">
          <span>{{ pullMessage }}</span>
        </div>
        <a-progress :percent="pullProgress" :status="progressStatus" />
        <div v-if="currentMirror" class="current-mirror">
          <span>{{ t('init.common.currentMirror', { mirror: currentMirror }) }}</span>
        </div>
      </div>

      <!-- 部署进度 -->
      <div v-if="deploying" class="deploy-progress">
        <p>{{ deployMessage }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  checking: boolean
  repoExists: boolean
  pulling: boolean
  deploying: boolean
  pullProgress: number
  pullMessage: string
  deployMessage: string
  currentMirror?: string
  progressStatus?: 'normal' | 'exception' | 'success'
}>()

const { t } = useI18n()
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

.check-status,
.deploy-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px 0;
}

.repo-status {
  padding: 12px 0;
}

.pull-progress {
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
</style>
