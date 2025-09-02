<template>
  <div class="step-panel">
    <h3>Python 运行环境</h3>
    <div v-if="!pythonInstalled" class="install-section">
      <p>需要安装 Python 3.13.0 运行环境</p>

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
            :class="{ active: selectedPythonMirror === mirror.key }"
            @click="selectedPythonMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h4>{{ mirror.name }}</h4>
                <a-tag v-if="mirror.recommended" color="gold" size="small">推荐</a-tag>
              </div>
              <div class="speed-badge" :class="getSpeedClass(mirror.speed)">
                <span v-if="mirror.speed === null && !testingSpeed">未测试</span>
                <span v-else-if="testingSpeed">测试中...</span>
                <span v-else-if="mirror.speed === 9999">超时</span>
                <span v-else>{{ mirror.speed }}ms</span>
              </div>
            </div>
            <div class="mirror-description">{{ mirror.description }}</div>
<!--            <div class="mirror-url">{{ mirror.url }}</div>-->
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
            :class="{ active: selectedPythonMirror === mirror.key }"
            @click="selectedPythonMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h4>{{ mirror.name }}</h4>
              </div>
              <div class="speed-badge" :class="getSpeedClass(mirror.speed)">
                <span v-if="mirror.speed === null && !testingSpeed">未测试</span>
                <span v-else-if="testingSpeed">测试中...</span>
                <span v-else-if="mirror.speed === 9999">超时</span>
                <span v-else>{{ mirror.speed }}ms</span>
              </div>
            </div>
            <div class="mirror-description">{{ mirror.description }}</div>
<!--            <div class="mirror-url">{{ mirror.url }}</div>-->
          </div>
        </div>
      </div>

      <div class="test-actions">
        <a-button @click="testPythonMirrorSpeed" :loading="testingSpeed" type="primary">
          {{ testingSpeed ? '测速中...' : '重新测速' }}
        </a-button>
        <span class="test-note">3秒无响应视为超时</span>
      </div>
    </div>
    <div v-else class="already-installed">
      <a-result status="success" title="Python已成功安装，无需继续安装" />
      <!--            <div class="reinstall-section">-->
      <!--                <a-button type="primary" danger @click="handleForceReinstall" :loading="reinstalling">-->
      <!--                    {{ reinstalling ? '正在重新安装...' : '强制重新安装' }}-->
      <!--                </a-button>-->
      <!--                <p class="reinstall-note">点击此按钮将删除现有Python环境并重新安装</p>-->
      <!--            </div>-->
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'
import { 
  PYTHON_MIRRORS, 
  getOfficialMirrors, 
  getMirrorMirrors,
  sortMirrorsBySpeedAndRecommendation,
  type MirrorConfig 
} from '@/config/mirrors'

const props = defineProps<{
  pythonInstalled: boolean
}>()

const pythonMirrors = ref<MirrorConfig[]>(PYTHON_MIRRORS)

// 按类型分组的镜像源
const officialMirrors = computed(() => getOfficialMirrors('python'))
const mirrorMirrors = computed(() => getMirrorMirrors('python'))

// 按速度和推荐排序的镜像源
const sortedOfficialMirrors = computed(() => sortMirrorsBySpeedAndRecommendation(officialMirrors.value))
const sortedMirrorMirrors = computed(() => sortMirrorsBySpeedAndRecommendation(mirrorMirrors.value))

const selectedPythonMirror = ref('aliyun')
const testingSpeed = ref(false)
const reinstalling = ref(false)

// 加载配置中的镜像源选择
async function loadMirrorConfig() {
  try {
    const config = await getConfig()
    selectedPythonMirror.value = config.selectedPythonMirror
    console.log('Python镜像源配置已加载:', selectedPythonMirror.value)
  } catch (error) {
    console.warn('加载Python镜像源配置失败:', error)
  }
}

// 保存镜像源选择
async function saveMirrorConfig() {
  try {
    await saveConfig({ selectedPythonMirror: selectedPythonMirror.value })
    console.log('Python镜像源配置已保存:', selectedPythonMirror.value)
  } catch (error) {
    console.warn('保存Python镜像源配置失败:', error)
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

async function testPythonMirrorSpeed() {
  testingSpeed.value = true
  try {
    const promises = pythonMirrors.value.map(async mirror => {
      mirror.speed = await testMirrorWithTimeout(mirror.url)
      return mirror
    })

    await Promise.all(promises)

    // 优先选择推荐的且速度最快的镜像源
    const sortedMirrors = sortMirrorsBySpeedAndRecommendation(pythonMirrors.value)
    const fastest = sortedMirrors.find(m => m.speed !== 9999)
    if (fastest) {
      selectedPythonMirror.value = fastest.key
      await saveMirrorConfig() // 保存最快的镜像源选择
    }
  } finally {
    testingSpeed.value = false
  }
}

function getSpeedClass(speed: number | null) {
  if (speed === null) return 'speed-unknown'
  if (speed === 9999) return 'speed-timeout'
  if (speed < 500) return 'speed-fast'
  if (speed < 1500) return 'speed-medium'
  return 'speed-slow'
}

// 强制重新安装Python
async function handleForceReinstall() {
  reinstalling.value = true
  try {
    console.log('开始强制重新安装Python')
    // 先删除现有Python目录
    const deleteResult = await window.electronAPI.deletePython()
    if (!deleteResult.success) {
      throw new Error(`删除Python目录失败: ${deleteResult.error}`)
    }

    // 重新下载安装Python
    const installResult = await window.electronAPI.downloadPython(selectedPythonMirror.value)
    if (!installResult.success) {
      throw new Error(`重新安装Python失败: ${installResult.error}`)
    }

    console.log('Python强制重新安装成功')
    // 通知父组件更新状态
    window.location.reload() // 简单的页面刷新来更新状态
  } catch (error) {
    console.error('Python强制重新安装失败:', error)
    // 这里可以添加错误提示
  } finally {
    reinstalling.value = false
  }
}

defineExpose({
  selectedPythonMirror,
  testPythonMirrorSpeed,
  handleForceReinstall,
})

// 组件挂载时加载配置并自动开始测速
onMounted(async () => {
  // 先加载配置
  await loadMirrorConfig()

  if (!props.pythonInstalled) {
    console.log('PythonStep 组件挂载，自动开始测速')
    setTimeout(() => {
      testPythonMirrorSpeed()
    }, 200) // 延迟200ms确保组件完全渲染
  }
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

.already-installed {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 200px;
  gap: 20px;
}

.reinstall-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.reinstall-note {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  text-align: center;
  margin: 0;
}
</style>