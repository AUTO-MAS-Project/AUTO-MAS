<template>
  <div class="step-panel">
    <h3>安装 Python 依赖包</h3>
    <div class="install-section">
      <p>通过 pip 安装项目所需的 Python 依赖包</p>

      <div class="mirror-grid">
        <div
          v-for="mirror in pipMirrors"
          :key="mirror.key"
          class="mirror-card"
          :class="{ active: selectedPipMirror === mirror.key }"
          @click="selectedPipMirror = mirror.key"
        >
          <div class="mirror-header">
            <h4>{{ mirror.name }}</h4>
            <div class="speed-badge" :class="getSpeedClass(mirror.speed)">
              <span v-if="mirror.speed === null && !testingPipSpeed">未测试</span>
              <span v-else-if="testingPipSpeed">测试中...</span>
              <span v-else-if="mirror.speed === 9999">超时</span>
              <span v-else>{{ mirror.speed }}ms</span>
            </div>
          </div>
          <div class="mirror-url">{{ mirror.url }}</div>
        </div>
      </div>

      <div class="test-actions">
        <a-button @click="testPipMirrorSpeed" :loading="testingPipSpeed" type="primary">
          {{ testingPipSpeed ? '测速中...' : '重新测速' }}
        </a-button>
        <span class="test-note">3秒无响应视为超时</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'

interface Mirror {
  key: string
  name: string
  url: string
  speed: number | null
}

import { PIP_MIRRORS } from '@/config/mirrors'

const pipMirrors = ref<Mirror[]>(PIP_MIRRORS)

const selectedPipMirror = ref('tsinghua')
const testingPipSpeed = ref(false)

// 加载配置中的镜像源选择
async function loadMirrorConfig() {
  try {
    const config = await getConfig()
    selectedPipMirror.value = config.selectedPipMirror
    console.log('pip镜像源配置已加载:', selectedPipMirror.value)
  } catch (error) {
    console.warn('加载pip镜像源配置失败:', error)
  }
}

// 保存镜像源选择
async function saveMirrorConfig() {
  try {
    await saveConfig({ selectedPipMirror: selectedPipMirror.value })
    console.log('pip镜像源配置已保存:', selectedPipMirror.value)
  } catch (error) {
    console.warn('保存pip镜像源配置失败:', error)
  }
}

async function testMirrorWithTimeout(url: string, timeout = 3000): Promise<number> {
  const startTime = Date.now()

  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    await fetch(url, {
      method: 'HEAD',
      mode: 'no-cors',
      signal: controller.signal,
    })

    clearTimeout(timeoutId)
    return Date.now() - startTime
  } catch (error) {
    return 9999 // 超时或失败
  }
}

async function testPipMirrorSpeed() {
  testingPipSpeed.value = true
  try {
    const promises = pipMirrors.value.map(async mirror => {
      mirror.speed = await testMirrorWithTimeout(mirror.url)
      return mirror
    })

    await Promise.all(promises)
    pipMirrors.value.sort((a, b) => (a.speed || 9999) - (b.speed || 9999))

    const fastest = pipMirrors.value.find(m => m.speed !== 9999)
    if (fastest) {
      selectedPipMirror.value = fastest.key
      await saveMirrorConfig() // 保存最快的镜像源选择
    }
  } finally {
    testingPipSpeed.value = false
  }
}

function getSpeedClass(speed: number | null) {
  if (speed === null) return 'speed-unknown'
  if (speed === 9999) return 'speed-timeout'
  if (speed < 500) return 'speed-fast'
  if (speed < 1500) return 'speed-medium'
  return 'speed-slow'
}

defineExpose({
  selectedPipMirror,
  testPipMirrorSpeed,
})

// 组件挂载时加载配置并自动开始测速
onMounted(async () => {
  // 先加载配置
  await loadMirrorConfig()

  console.log('DependenciesStep 组件挂载，自动开始测速')
  setTimeout(() => {
    testPipMirrorSpeed()
  }, 200) // 延迟200ms确保组件完全渲染
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

.install-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.install-section p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.mirror-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
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
  color: var(--ant-color-text-tertiary);
}

.speed-badge.speed-fast {
  color: var(--ant-color-success);
}

.speed-badge.speed-medium {
  color: var(--ant-color-warning);
}

.speed-badge.speed-slow {
  color: var(--ant-color-error);
}

.speed-badge.speed-timeout {
  color: var(--ant-color-error);
}

.mirror-url {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  word-break: break-all;
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
</style>