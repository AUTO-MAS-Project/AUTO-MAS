<template>
  <div class="mirror-test-container">
    <div class="test-header">
      <div class="header-content">
        <div class="title-section">
          <h2>镜像配置测试页面</h2>
          <p>用于测试云端镜像配置拉取功能</p>
        </div>
        <a-button size="large" @click="goBack">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回设置
        </a-button>
      </div>
    </div>

    <div class="test-content">
      <a-card title="配置状态" style="margin-bottom: 16px">
        <a-descriptions :column="1" bordered>
          <a-descriptions-item label="配置来源">
            <a-tag :color="configStatus.source === 'cloud' ? 'green' : 'orange'">
              {{ configStatus.source === 'cloud' ? '云端配置' : '本地兜底配置' }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item v-if="configStatus.version" label="配置版本">
            {{ configStatus.version }}
          </a-descriptions-item>
          <a-descriptions-item v-if="configStatus.lastUpdated" label="最后更新">
            {{ new Date(configStatus.lastUpdated).toLocaleString() }}
          </a-descriptions-item>
        </a-descriptions>
      </a-card>

      <a-card title="操作" style="margin-bottom: 16px">
        <a-space>
          <a-button type="primary" :loading="refreshing" @click="refreshConfig">
            刷新云端配置
          </a-button>
          <a-button @click="updateStatus"> 更新状态 </a-button>
          <a-button @click="testCloudUrl"> 测试云端URL </a-button>
        </a-space>
      </a-card>

      <a-card v-if="currentConfig" title="当前镜像配置">
        <a-tabs>
          <a-tab-pane key="git" tab="Git镜像">
            <a-table
              :data-source="currentConfig.mirrors.git"
              :columns="mirrorColumns"
              :pagination="false"
              size="small"
            />
          </a-tab-pane>
          <a-tab-pane key="python" tab="Python镜像">
            <a-table
              :data-source="currentConfig.mirrors.python"
              :columns="mirrorColumns"
              :pagination="false"
              size="small"
            />
          </a-tab-pane>
          <a-tab-pane key="pip" tab="PIP镜像">
            <a-table
              :data-source="currentConfig.mirrors.pip"
              :columns="mirrorColumns"
              :pagination="false"
              size="small"
            />
          </a-tab-pane>
        </a-tabs>
      </a-card>

      <a-card v-if="testLogs.length > 0" title="测试日志">
        <div class="test-logs">
          <div v-for="(log, index) in testLogs" :key="index" :class="['log-item', log.type]">
            <span class="log-time">{{ log.time }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import { mirrorManager } from '@/utils/mirrorManager'
import { cloudConfigManager, type CloudMirrorConfig } from '@/utils/cloudConfigManager'
import { getLogger } from '@/utils/logger'

const logger = getLogger('镜像测试')

const router = useRouter()

interface TestLog {
  time: string
  message: string
  type: 'info' | 'success' | 'error' | 'warning'
}

const configStatus = ref({
  isUsingCloudConfig: false,
  version: '',
  lastUpdated: '',
  source: 'fallback' as 'cloud' | 'fallback',
})

const currentConfig = ref<CloudMirrorConfig | null>(null)
const refreshing = ref(false)
const testLogs = ref<TestLog[]>([])

const mirrorColumns = [
  {
    title: 'Key',
    dataIndex: 'key',
    key: 'key',
    width: 120,
  },
  {
    title: '名称',
    dataIndex: 'name',
    key: 'name',
    width: 150,
  },
  {
    title: 'URL',
    dataIndex: 'url',
    key: 'url',
    ellipsis: true,
  },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
    width: 80,
  },
  {
    title: '连通性',
    dataIndex: 'chinaConnectivity',
    key: 'chinaConnectivity',
    width: 100,
  },
]

const addLog = (message: string, type: TestLog['type'] = 'info') => {
  testLogs.value.unshift({
    time: new Date().toLocaleTimeString(),
    message,
    type,
  })

  // 限制日志数量
  if (testLogs.value.length > 50) {
    testLogs.value = testLogs.value.slice(0, 50)
  }
}

const updateStatus = () => {
  const status = mirrorManager.getConfigStatus()
  configStatus.value = status
  currentConfig.value = cloudConfigManager.getCurrentConfig()
  addLog('状态已更新', 'info')
}

const refreshConfig = async () => {
  refreshing.value = true
  addLog('开始刷新云端配置...', 'info')

  try {
    const result = await mirrorManager.refreshCloudConfig()

    if (result.success) {
      message.success('配置刷新成功')
      addLog('云端配置刷新成功', 'success')
      updateStatus()
    } else {
      message.warning(result.error || '刷新失败')
      addLog(`刷新失败: ${result.error}`, 'warning')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : '未知错误'
    message.error('刷新配置失败')
    addLog(`刷新配置失败: ${errorMsg}`, 'error')
  } finally {
    refreshing.value = false
  }
}

const testCloudUrl = async () => {
  addLog('测试云端URL连通性...', 'info')

  try {
    const response = await fetch('https://download.auto-mas.top/d/AUTO-MAS/Server/mirrors.json', {
      method: 'HEAD',
      mode: 'no-cors',
    })
    addLog('云端URL连通性测试完成', 'success')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : '连接失败'
    addLog(`云端URL连通性测试失败: ${errorMsg}`, 'error')
  }
}

const goBack = () => {
  router.push('/settings')
}

onMounted(() => {
  updateStatus()
  addLog('镜像配置测试页面已加载', 'info')
})
</script>

<style scoped>
.mirror-test-container {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.test-header {
  margin-bottom: 24px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.title-section {
  flex: 1;
}

.test-header h2 {
  margin-bottom: 8px;
}

.test-logs {
  max-height: 300px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.log-item {
  display: flex;
  margin-bottom: 4px;
  padding: 4px 8px;
  border-radius: 4px;
}

.log-item.success {
  color: #52c41a;
}

.log-item.error {
  color: #ff4d4f;
}

.log-item.warning {
  color: #faad14;
}

.log-time {
  margin-right: 8px;
  min-width: 80px;
}

.log-message {
  flex: 1;
}
</style>
