<template>
  <div class="step-panel">
    <h3>{{ title }}</h3>
    <div v-if="!installed" class="install-section">
      <p>{{ description }}</p>

      <!-- 环境检查状态 -->
      <div v-if="checking" class="check-status">
        <p>正在检查环境...</p>
      </div>

      <!-- 镜像源选择 (仅Python显示) -->
      <template v-if="!checking && showMirrorSelection">
        <div class="mirror-section">
          <div class="section-header">
            <h4>镜像源</h4>
            <a-tag color="green">推荐使用</a-tag>
          </div>
          <div class="mirror-grid">
            <div
              v-for="mirror in sortedMirrorMirrors"
              :key="mirror.key"
              class="mirror-card"
              :class="{ active: selectedMirror === mirror.key }"
              @click="handleMirrorSelect(mirror.key)"
            >
              <div class="mirror-header">
                <div class="mirror-title">
                  <h4>{{ mirror.name }}</h4>
                  <a-tag v-if="mirror.recommended" color="gold" size="small">推荐</a-tag>
                </div>
                <div class="speed-badge" :class="getSpeedClass(mirror.speed ?? null)">
                  <span v-if="mirror.speed === null && !testingSpeed">未测试</span>
                  <span v-else-if="testingSpeed">测试中...</span>
                  <span v-else-if="mirror.speed === 9999">超时</span>
                  <span v-else>{{ mirror.speed }}ms</span>
                </div>
              </div>
              <div class="mirror-description">{{ mirror.description }}</div>
            </div>
          </div>
        </div>

        <div class="mirror-section">
          <div class="section-header">
            <h4>官方源</h4>
            <a-tag color="orange">中国大陆连通性不佳</a-tag>
          </div>
          <div class="mirror-grid">
            <div
              v-for="mirror in sortedOfficialMirrors"
              :key="mirror.key"
              class="mirror-card"
              :class="{ active: selectedMirror === mirror.key }"
              @click="handleMirrorSelect(mirror.key)"
            >
              <div class="mirror-header">
                <div class="mirror-title">
                  <h4>{{ mirror.name }}</h4>
                </div>
                <div class="speed-badge" :class="getSpeedClass(mirror.speed ?? null)">
                  <span v-if="mirror.speed === null && !testingSpeed">未测试</span>
                  <span v-else-if="testingSpeed">测试中...</span>
                  <span v-else-if="mirror.speed === 9999">超时</span>
                  <span v-else>{{ mirror.speed }}ms</span>
                </div>
              </div>
              <div class="mirror-description">{{ mirror.description }}</div>
            </div>
          </div>
        </div>

        <div class="test-actions">
          <a-button :loading="testingSpeed" type="primary" @click="handleTestSpeed">
            {{ testingSpeed ? '测速中...' : '重新测速' }}
          </a-button>
          <span class="test-note">3秒无响应视为超时</span>
        </div>
      </template>

      <!-- 下载进度 -->
      <div v-if="downloading" class="download-progress">
        <div class="progress-info">
          <span>{{ downloadMessage }}</span>
          <span v-if="downloadSpeed">{{ downloadSpeed }}</span>
        </div>
        <a-progress :percent="downloadProgress" :status="progressStatus" />
        <div v-if="currentMirror" class="current-mirror">
          <span>当前使用: {{ currentMirror }}</span>
        </div>
      </div>

      <!-- 安装进度 -->
      <div v-if="installing" class="install-progress">
        <p>{{ installMessage }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { sortMirrorsBySpeedAndRecommendation, type MirrorConfig } from '@/config/mirrors.ts'

const props = defineProps<{
  title: string
  description: string
  installed: boolean
  checking: boolean
  downloading: boolean
  installing: boolean
  downloadProgress: number
  downloadMessage: string
  downloadSpeed?: string
  installMessage: string
  currentMirror?: string
  progressStatus?: 'normal' | 'exception' | 'success'
  showMirrorSelection: boolean
  mirrors: MirrorConfig[]
  selectedMirror: string
  testingSpeed: boolean
}>()

const emit = defineEmits<{
  'update:selectedMirror': [value: string]
  testSpeed: []
}>()

const officialMirrors = computed(() => props.mirrors.filter(m => m.type === 'official'))
const mirrorMirrors = computed(() => props.mirrors.filter(m => m.type === 'mirror'))

const sortedOfficialMirrors = computed(() =>
  sortMirrorsBySpeedAndRecommendation(officialMirrors.value)
)
const sortedMirrorMirrors = computed(() =>
  sortMirrorsBySpeedAndRecommendation(mirrorMirrors.value)
)

function handleMirrorSelect(key: string) {
  emit('update:selectedMirror', key)
}

function handleTestSpeed() {
  emit('testSpeed')
}

function getSpeedClass(speed: number | null) {
  if (speed === null) return 'speed-unknown'
  if (speed === 9999) return 'speed-timeout'
  if (speed < 500) return 'speed-fast'
  if (speed < 1500) return 'speed-medium'
  return 'speed-slow'
}
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

.check-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px 0;
}

.mirror-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.mirror-card {
  padding: 16px;
  border: 2px solid var(--ant-color-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--ant-color-bg-container);
}

.mirror-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.mirror-card.active {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.mirror-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.mirror-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mirror-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.speed-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.speed-badge.speed-unknown {
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text-tertiary);
}

.speed-badge.speed-fast {
  background: var(--ant-color-success-bg);
  color: var(--ant-color-success);
}

.speed-badge.speed-medium {
  background: var(--ant-color-warning-bg);
  color: var(--ant-color-warning);
}

.speed-badge.speed-slow {
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
}

.speed-badge.speed-timeout {
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
}

.mirror-description {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  line-height: 1.4;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.section-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.test-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
}

.test-note {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.download-progress,
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

.install-progress {
  align-items: center;
  padding: 40px;
}

.already-installed {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>
