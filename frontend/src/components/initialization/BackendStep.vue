<template>
  <div class="step-panel">
    <h3>获取后端源码</h3>
    <div class="install-section">
      <p>{{ backendExists ? '更新最新的后端代码' : '获取后端源代码' }}</p>

      <!-- 镜像源 -->
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
            :class="{ active: selectedGitMirror === mirror.key }"
            @click="selectedGitMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h4>{{ mirror.name }}</h4>
                <a-tag v-if="mirror.recommended" color="gold" size="small">推荐</a-tag>
              </div>
              <div class="speed-badge" :class="getSpeedClass(mirror.speed)">
                <span v-if="mirror.speed === null && !testingGitSpeed">未测试</span>
                <span v-else-if="testingGitSpeed">测试中...</span>
                <span v-else-if="mirror.speed === 9999">超时</span>
                <span v-else>{{ mirror.speed }}ms</span>
              </div>
            </div>
            <div class="mirror-description">{{ mirror.description }}</div>
            <div class="mirror-url">{{ mirror.url }}</div>
          </div>
        </div>
      </div>

      <!-- 官方源 -->
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
            :class="{ active: selectedGitMirror === mirror.key }"
            @click="selectedGitMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h4>{{ mirror.name }}</h4>
              </div>
              <div class="speed-badge" :class="getSpeedClass(mirror.speed)">
                <span v-if="mirror.speed === null && !testingGitSpeed">未测试</span>
                <span v-else-if="testingGitSpeed">测试中...</span>
                <span v-else-if="mirror.speed === 9999">超时</span>
                <span v-else>{{ mirror.speed }}ms</span>
              </div>
            </div>
            <div class="mirror-description">{{ mirror.description }}</div>
            <div class="mirror-url">{{ mirror.url }}</div>
          </div>
        </div>
      </div>

      <div class="test-actions">
        <a-button @click="testGitMirrorSpeed" :loading="testingGitSpeed" type="primary">
          {{ testingGitSpeed ? '测速中...' : '开始测速' }}
        </a-button>
        <span class="test-note">3秒无响应视为超时</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'
import { 
  GIT_MIRRORS, 
  getOfficialMirrors, 
  getMirrorMirrors,
  sortMirrorsBySpeedAndRecommendation,
  type MirrorConfig 
} from '@/config/mirrors'

defineProps<{
  backendExists: boolean
}>()

const gitMirrors = ref<MirrorConfig[]>(GIT_MIRRORS)

// 按类型分组的镜像源
const officialMirrors = computed(() => getOfficialMirrors('git'))
const mirrorMirrors = computed(() => getMirrorMirrors('git'))

// 按速度和推荐排序的镜像源
const sortedOfficialMirrors = computed(() => sortMirrorsBySpeedAndRecommendation(officialMirrors.value))
const sortedMirrorMirrors = computed(() => sortMirrorsBySpeedAndRecommendation(mirrorMirrors.value))

const selectedGitMirror = ref('ghproxy_edgeone')
const testingGitSpeed = ref(false)

// 加载配置中的镜像源选择
async function loadMirrorConfig() {
  try {
    const config = await getConfig()
    selectedGitMirror.value = config.selectedGitMirror
    console.log('Git镜像源配置已加载:', selectedGitMirror.value)
  } catch (error) {
    console.warn('加载Git镜像源配置失败:', error)
  }
}

// 保存镜像源选择
async function saveMirrorConfig() {
  try {
    await saveConfig({ selectedGitMirror: selectedGitMirror.value })
    console.log('Git镜像源配置已保存:', selectedGitMirror.value)
  } catch (error) {
    console.warn('保存Git镜像源配置失败:', error)
  }
}

async function testMirrorWithTimeout(url: string, timeout = 3000): Promise<number> {
  const startTime = Date.now()

  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    await fetch(url.replace('.git', ''), {
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

async function testGitMirrorSpeed() {
  testingGitSpeed.value = true
  try {
    const promises = gitMirrors.value.map(async mirror => {
      mirror.speed = await testMirrorWithTimeout(mirror.url)
      return mirror
    })

    await Promise.all(promises)

    // 优先选择推荐的且速度最快的镜像源
    const sortedMirrors = sortMirrorsBySpeedAndRecommendation(gitMirrors.value)
    const fastest = sortedMirrors.find(m => m.speed !== 9999)
    if (fastest) {
      selectedGitMirror.value = fastest.key
      await saveMirrorConfig() // 保存最快的镜像源选择
    }
  } finally {
    testingGitSpeed.value = false
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
  selectedGitMirror,
  testGitMirrorSpeed,
  gitMirrors,
})

// 组件挂载时加载配置并自动开始测速
onMounted(async () => {
  // 先加载配置
  await loadMirrorConfig()

  console.log('BackendStep 组件挂载，自动开始测速')
  setTimeout(() => {
    testGitMirrorSpeed()
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

.mirror-description {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  margin-bottom: 4px;
  line-height: 1.4;
}

.mirror-url {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  word-break: break-all;
}

.mirror-section {
  margin-bottom: 24px;
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
</style>