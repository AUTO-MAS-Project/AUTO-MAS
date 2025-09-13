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
              <div class="speed-badge" :class="getSpeedClass(mirror.speed ?? null)">
                <span v-if="mirror.speed === null && !testingGitSpeed">未测试</span>
                <span v-else-if="testingGitSpeed">测试中...</span>
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
            :class="{ active: selectedGitMirror === mirror.key }"
            @click="selectedGitMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h4>{{ mirror.name }}</h4>
              </div>
              <div class="speed-badge" :class="getSpeedClass(mirror.speed ?? null)">
                <span v-if="mirror.speed === null && !testingGitSpeed">未测试</span>
                <span v-else-if="testingGitSpeed">测试中...</span>
                <span v-else-if="mirror.speed === 9999">超时</span>
                <span v-else>{{ mirror.speed }}ms</span>
              </div>
            </div>
            <div class="mirror-description">{{ mirror.description }}</div>
<!--            <div class="mirror-url">{{ mirror.url }}</div>-->
          </div>
        </div>
      </div>

      <!-- 自定义镜像源 -->
      <div class="mirror-section">
        <div class="section-header">
          <h4>自定义镜像源</h4>
          <a-tag color="blue">手动添加</a-tag>
        </div>
        <div class="custom-mirror-input">
          <a-input-group compact>
            <a-input
              v-model:value="customMirrorUrl"
              placeholder="输入镜像域名或完整Git地址，如：ghproxy.com 或 https://ghproxy.com/https://github.com/AUTO-MAS-Project/AUTO-MAS.git"
              style="width: calc(100% - 100px)"
              @pressEnter="addCustomMirror"
            />
            <a-button 
              type="primary" 
              @click="addCustomMirror"
              :loading="addingCustomMirror"
              style="width: 100px"
            >
              添加
            </a-button>
          </a-input-group>
        </div>
        
        <!-- 显示自定义镜像源 -->
        <div v-if="customMirrors.length > 0" class="mirror-grid" style="margin-top: 16px;">
          <div
            v-for="mirror in customMirrors"
            :key="mirror.key"
            class="mirror-card custom-mirror"
            :class="{ active: selectedGitMirror === mirror.key }"
            @click="selectedGitMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h4>{{ mirror.name }}</h4>
                <a-tag color="blue" size="small">自定义</a-tag>
              </div>
              <div class="mirror-actions">
                <div class="speed-badge" :class="getSpeedClass(mirror.speed ?? null)">
                  <span v-if="mirror.speed === null && !testingGitSpeed">未测试</span>
                  <span v-else-if="testingGitSpeed">测试中...</span>
                  <span v-else-if="mirror.speed === 9999">超时</span>
                  <span v-else>{{ mirror.speed }}ms</span>
                </div>
                <a-button 
                  type="text" 
                  size="small" 
                  danger
                  @click.stop="removeCustomMirror(mirror.key)"
                >
                  删除
                </a-button>
              </div>
            </div>
            <div class="mirror-description">{{ mirror.description }}</div>
          </div>
        </div>
      </div>

      <div class="test-actions">
        <a-button @click="testGitMirrorSpeed" :loading="testingGitSpeed" type="primary">
          {{ testingGitSpeed ? '测速中...' : '重新测速' }}
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

// 自定义镜像源相关
const customMirrorUrl = ref('')
const customMirrors = ref<MirrorConfig[]>([])
const addingCustomMirror = ref(false)

// 加载配置中的镜像源选择
async function loadMirrorConfig() {
  try {
    const config = await getConfig()
    selectedGitMirror.value = config.selectedGitMirror || 'ghproxy_edgeone'
    
    // 加载自定义镜像源
    if (config.customGitMirrors && Array.isArray(config.customGitMirrors)) {
      customMirrors.value = config.customGitMirrors
      // 将自定义镜像源添加到gitMirrors中
      gitMirrors.value = [...GIT_MIRRORS, ...customMirrors.value]
    }
    
    console.log('Git镜像源配置已加载:', selectedGitMirror.value)
    console.log('自定义镜像源已加载:', customMirrors.value.length, '个')
  } catch (error) {
    console.warn('加载Git镜像源配置失败:', error)
  }
}

// 保存镜像源选择
async function saveMirrorConfig() {
  try {
    await saveConfig({ 
      selectedGitMirror: selectedGitMirror.value,
      customGitMirrors: customMirrors.value
    })
    console.log('Git镜像源配置已保存:', selectedGitMirror.value)
    console.log('自定义镜像源已保存:', customMirrors.value.length, '个')
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

// 处理自定义镜像源URL
function processCustomMirrorUrl(input: string): string {
  const trimmedInput = input.trim()
  
  // 如果已经是完整的Git地址且以.git结尾，直接返回
  if (trimmedInput.includes('github.com/AUTO-MAS-Project/AUTO-MAS') && trimmedInput.endsWith('.git')) {
    return trimmedInput
  }
  
  // 如果是完整的Git地址但没有.git结尾，添加.git
  if (trimmedInput.includes('github.com/AUTO-MAS-Project/AUTO-MAS')) {
    return trimmedInput.endsWith('.git') ? trimmedInput : trimmedInput + '.git'
  }
  
  // 如果只是域名，拼接完整地址
  let domain = trimmedInput
  
  // 移除协议前缀
  domain = domain.replace(/^https?:\/\//, '')
  
  // 移除尾部斜杠
  domain = domain.replace(/\/$/, '')
  
  // 拼接完整地址
  return `https://${domain}/https://github.com/AUTO-MAS-Project/AUTO-MAS.git`
}

// 添加自定义镜像源
async function addCustomMirror() {
  if (!customMirrorUrl.value.trim()) {
    return
  }
  
  addingCustomMirror.value = true
  
  try {
    const processedUrl = processCustomMirrorUrl(customMirrorUrl.value)
    
    // 检查是否已存在
    const existingMirror = [...gitMirrors.value, ...customMirrors.value].find(
      m => m.url === processedUrl
    )
    
    if (existingMirror) {
      console.warn('镜像源已存在:', processedUrl)
      customMirrorUrl.value = ''
      return
    }
    
    // 生成镜像源配置
    const customKey = `custom_${Date.now()}`
    const customName = extractDomainName(customMirrorUrl.value)
    
    const newMirror: MirrorConfig = {
      key: customKey,
      name: `${customName} (自定义)`,
      url: processedUrl,
      speed: null,
      type: 'mirror',
      chinaConnectivity: 'good',
      description: `用户自定义的镜像源: ${customName}`
    }
    
    // 添加到自定义镜像源列表
    customMirrors.value.push(newMirror)
    
    // 更新完整的镜像源列表
    gitMirrors.value = [...GIT_MIRRORS, ...customMirrors.value]
    
    // 自动选择新添加的镜像源
    selectedGitMirror.value = customKey
    
    // 保存配置
    await saveMirrorConfig()
    
    // 清空输入框
    customMirrorUrl.value = ''
    
    console.log('自定义镜像源添加成功:', newMirror)
    
  } catch (error) {
    console.error('添加自定义镜像源失败:', error)
  } finally {
    addingCustomMirror.value = false
  }
}

// 提取域名作为显示名称
function extractDomainName(url: string): string {
  try {
    // 移除协议前缀
    let domain = url.replace(/^https?:\/\//, '')
    
    // 如果包含路径，只取域名部分
    domain = domain.split('/')[0]
    
    // 移除端口号
    domain = domain.split(':')[0]
    
    return domain || '自定义镜像'
  } catch {
    return '自定义镜像'
  }
}

// 删除自定义镜像源
async function removeCustomMirror(key: string) {
  try {
    // 从自定义镜像源列表中移除
    customMirrors.value = customMirrors.value.filter(m => m.key !== key)
    
    // 更新完整的镜像源列表
    gitMirrors.value = [...GIT_MIRRORS, ...customMirrors.value]
    
    // 如果当前选中的是被删除的镜像源，切换到默认镜像源
    if (selectedGitMirror.value === key) {
      selectedGitMirror.value = 'ghproxy_edgeone'
    }
    
    // 保存配置
    await saveMirrorConfig()
    
    console.log('自定义镜像源删除成功:', key)
    
  } catch (error) {
    console.error('删除自定义镜像源失败:', error)
  }
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

.custom-mirror-input {
  margin-bottom: 16px;
}

.custom-mirror-help {
  margin-top: 8px;
}

.custom-mirror-help code {
  background: var(--ant-color-fill-alter);
  padding: 2px 4px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.mirror-card.custom-mirror {
  border-color: var(--ant-color-primary-border);
}

.mirror-card.custom-mirror:hover {
  border-color: var(--ant-color-primary);
}

.mirror-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>