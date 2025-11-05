<template>
  <div class="step-panel">
    <h3>安装 Python 依赖包</h3>
    <div class="install-section">
      <p>通过 pip 安装项目所需的 Python 依赖包</p>

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
            :class="{ active: selectedPipMirror === mirror.key }"
            @click="selectedPipMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h4>{{ mirror.name }}</h4>
                <a-tag v-if="mirror.recommended" color="gold" size="small">推荐</a-tag>
              </div>
              <div class="speed-badge" :class="getSpeedClass(mirror.speed ?? null)">
                <span v-if="mirror.speed === null && !testingPipSpeed">未测试</span>
                <span v-else-if="testingPipSpeed">测试中...</span>
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
            :class="{ active: selectedPipMirror === mirror.key }"
            @click="selectedPipMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h4>{{ mirror.name }}</h4>
              </div>
              <div class="speed-badge" :class="getSpeedClass(mirror.speed ?? null)">
                <span v-if="mirror.speed === null && !testingPipSpeed">未测试</span>
                <span v-else-if="testingPipSpeed">测试中...</span>
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
        <a-button :loading="testingPipSpeed" type="primary" @click="testPipMirrorSpeed">
          {{ testingPipSpeed ? '测速中...' : '重新测速' }}
        </a-button>
        <span class="test-note">3秒无响应视为超时</span>
      </div>

      <!-- 跳过按钮 -->
      <div class="skip-section">
        <a-alert
          message="跳过此步骤"
          description="如果您已经手动安装了 Python 依赖包，可以跳过此步骤。跳过后将标记依赖为已安装。"
          type="warning"
          show-icon
        />
        <a-button style="margin-top: 12px" type="dashed" danger @click="handleSkip">
          跳过安装依赖包
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getConfig, saveConfig } from '@/utils/config.ts'
import { sortMirrorsBySpeedAndRecommendation, type MirrorConfig } from '@/config/mirrors.ts'
import { mirrorManager } from '@/utils/mirrorManager.ts'

const pipMirrors = ref<MirrorConfig[]>([])

// 按类型分组的镜像源
const officialMirrors = computed(() => pipMirrors.value.filter(m => m.type === 'official'))
const mirrorMirrors = computed(() => pipMirrors.value.filter(m => m.type === 'mirror'))

// 按速度和推荐排序的镜像源
const sortedOfficialMirrors = computed(() =>
  sortMirrorsBySpeedAndRecommendation(officialMirrors.value)
)
const sortedMirrorMirrors = computed(() => sortMirrorsBySpeedAndRecommendation(mirrorMirrors.value))

const selectedPipMirror = ref('aliyun')
const testingPipSpeed = ref(false)

// 加载配置中的镜像源选择
async function loadMirrorConfig() {
  try {
    // 从镜像管理器获取最新的pip镜像源配置（包含云端数据）
    const cloudMirrors = mirrorManager.getMirrors('pip')
    pipMirrors.value = [...cloudMirrors]

    const config = await getConfig()
    selectedPipMirror.value = config.selectedPipMirror || 'aliyun'
    console.log('pip镜像源配置已加载:', selectedPipMirror.value)
    console.log('云端pip镜像源已加载:', cloudMirrors.length, '个')
    console.log(
      '云端pip镜像源详情:',
      cloudMirrors.map(m => ({ name: m.name, key: m.key }))
    )
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

    // 优先选择推荐的且速度最快的镜像源
    const sortedMirrors = sortMirrorsBySpeedAndRecommendation(pipMirrors.value)
    const fastest = sortedMirrors.find(m => m.speed !== 9999)
    if (fastest) {
      selectedPipMirror.value = fastest.key
      await saveMirrorConfig() // 保存最快的镜像源选择
    }
  } finally {
    testingPipSpeed.value = false
  }
}

const emit = defineEmits<{
  skip: []
}>()

async function handleSkip() {
  try {
    await saveConfig({ dependenciesInstalled: true })
    console.log('用户跳过依赖安装步骤')
    emit('skip')
  } catch (error) {
    console.error('保存配置失败:', error)
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
  handleSkip,
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

.skip-section {
  margin-top: 24px;
}

.skip-section a-alert {
  margin-bottom: 12px;
}
</style>
