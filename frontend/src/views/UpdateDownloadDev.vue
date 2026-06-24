<template>
  <div class="update-download-dev-page">
    <a-flex justify="space-between" align="center" class="page-header">
      <div>
        <a-typography-title :level="3">更新下载测试台</a-typography-title>
        <a-typography-text type="secondary">
          真实下载可手动输入目标版本；模拟区只改前端状态，不访问后端。
        </a-typography-text>
      </div>
      <a-space>
        <a-button @click="open">恢复下载弹窗</a-button>
        <a-button @click="resetSimulation">重置状态</a-button>
      </a-space>
    </a-flex>

    <a-row :gutter="16" class="summary-row">
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="下载状态" :value="statusLabel" />
          <a-tag :color="statusColor" class="status-tag">{{ status }}</a-tag>
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="目标版本" :value="latestVersion || realTargetVersion || '未设置'" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="下载来源" :value="sourceLabel || '尚无来源'" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="弹窗状态" :value="modalVisible ? '显示中' : '已隐藏'" />
        </a-card>
      </a-col>
    </a-row>

    <a-card title="当前下载状态" class="section-card">
      <a-space direction="vertical" size="middle" class="full-width">
        <a-progress :percent="progressPercent" />
        <a-descriptions bordered size="small" :column="3">
          <a-descriptions-item label="已下载">
            {{ formatBytes(downloadedSize) }} / {{ formatBytes(fileSize) }}
          </a-descriptions-item>
          <a-descriptions-item label="速度">{{ formatSpeed(speed) }}</a-descriptions-item>
          <a-descriptions-item label="标题栏会显示">
            {{ titleBarPreview }}
          </a-descriptions-item>
          <a-descriptions-item label="失败原因" :span="3">
            {{ failureReason || '无' }}
          </a-descriptions-item>
        </a-descriptions>
      </a-space>
    </a-card>

    <a-alert
      type="warning"
      show-icon
      message="真实下载会调用后端并下载你输入的版本包。确认版本存在后再开始。"
      class="section-alert"
    />

    <a-card title="真实目标版本下载" class="section-card">
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="10">
            <a-form-item label="目标版本">
              <a-input
                v-model:value="realTargetVersion"
                placeholder="例如 v5.4.0-beta.1"
                allow-clear
              />
            </a-form-item>
          </a-col>
          <a-col :span="14">
            <a-form-item label="真实操作">
              <a-space wrap>
                <a-button :loading="isChecking" @click="runRealCheck">真实检查更新</a-button>
                <a-button @click="useCheckedVersion">填入检查到的版本</a-button>
                <a-button
                  type="primary"
                  :disabled="!realTargetVersion"
                  @click="confirmRealDownload"
                >
                  下载输入版本
                </a-button>
                <a-button danger :disabled="status !== 'downloading'" @click="confirmRealCancel">
                  真实取消下载
                </a-button>
                <a-button
                  :disabled="status !== 'downloading' || source === 'CNB'"
                  @click="confirmRealSwitch"
                >
                  真实切换 CNB
                </a-button>
                <a-button :disabled="status !== 'completed'" @click="confirmRealInstall">
                  启动真实安装
                </a-button>
              </a-space>
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-card>

    <a-alert
      type="info"
      show-icon
      message="安全模拟不会访问后端，可用于快速检查弹窗、标题栏和低速提示。"
      class="section-alert"
    />

    <a-card title="安全模拟" class="section-card">
      <a-space direction="vertical" size="large" class="full-width">
        <a-space wrap>
          <a-button type="primary" @click="simulateUpdateAvailable(simulatedVersion)">
            触发版本更新提示
          </a-button>
          <a-button @click="simulateStatus('cancelling')">模拟取消中</a-button>
          <a-button danger @click="simulateFailure('开发测试：模拟下载失败')">
            模拟下载失败
          </a-button>
          <a-button @click="simulateCompletion">模拟下载完成</a-button>
          <a-button @click="background">模拟后台下载</a-button>
        </a-space>

        <a-form layout="vertical">
          <a-row :gutter="16">
            <a-col :span="6">
              <a-form-item label="模拟版本">
                <a-input v-model:value="simulatedVersion" />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="下载源">
                <a-select v-model:value="simulatedSource" :options="sourceOptions" />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="进度">
                <a-input-number
                  v-model:value="simulatedPercent"
                  :min="0"
                  :max="100"
                  addon-after="%"
                  class="full-width"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="速度">
                <a-input-number
                  v-model:value="simulatedSpeedKb"
                  :min="0"
                  addon-after="KB/s"
                  class="full-width"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-space>
            <a-button
              type="primary"
              @click="simulateProgress(simulatedSource, simulatedPercent, simulatedSpeedKb * 1024)"
            >
              应用模拟进度
            </a-button>
            <a-button @click="startLowSpeedSimulation">模拟当前源持续低速</a-button>
          </a-space>
        </a-form>
      </a-space>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { useUpdateChecker, useUpdateModal } from '@/composables/useUpdateChecker'
import { useUpdateDownload } from '@/composables/useUpdateDownload'
import { useUpdateDownloadDevtools } from '@/composables/updateDownloadDevtools'

type SimulatedSource = 'GitHub' | 'CNB' | 'MirrorChyan' | 'AutoSite'

const {
  status,
  modalVisible,
  source,
  sourceLabel,
  downloadedSize,
  fileSize,
  speed,
  progressPercent,
  failureReason,
  latestVersion,
  formatBytes,
  formatSpeed,
  start,
  cancel,
  background,
  open,
  switchToCnb,
  install,
} = useUpdateDownload()
const { checkUpdate } = useUpdateChecker()
const { latestVersion: availableVersion, updateData: availableUpdateData } = useUpdateModal()
const {
  simulateUpdateAvailable,
  simulateProgress,
  simulateStatus,
  simulateFailure,
  simulateCompletion,
  resetSimulation,
} = useUpdateDownloadDevtools()

const realTargetVersion = ref('')
const simulatedVersion = ref('v9.9.9')
const simulatedSource = ref<SimulatedSource>('GitHub')
const simulatedPercent = ref(46.8)
const simulatedSpeedKb = ref(40)
const isChecking = ref(false)
let lowSpeedTimer: ReturnType<typeof setTimeout> | null = null

const sourceOptions = [
  { label: 'GitHub', value: 'GitHub' },
  { label: 'CNB', value: 'CNB' },
  { label: 'Mirror 酱', value: 'MirrorChyan' },
  { label: '自建源', value: 'AutoSite' },
]

const statusLabels = {
  idle: '空闲',
  downloading: '下载中',
  cancelling: '取消中',
  switchingSource: '切源中',
  completed: '已完成',
  failed: '失败',
}

const statusLabel = computed(() => statusLabels[status.value])
const statusColor = computed(() => {
  if (status.value === 'completed') return 'green'
  if (status.value === 'failed') return 'red'
  if (status.value === 'idle') return 'default'
  return 'blue'
})

const titleBarPreview = computed(() => {
  if (status.value === 'completed') return '下载完成，点击安装'
  if (status.value === 'failed') return '下载失败，点击查看'
  if (status.value === 'switchingSource') return '正在切换至 CNB 源'
  if (status.value === 'cancelling') return '正在取消下载'
  if (status.value === 'downloading') {
    const sourceText = sourceLabel.value ? `从 ${sourceLabel.value}` : ''
    return `正在${sourceText}下载 ${progressPercent.value.toFixed(1)}%`
  }
  return '检测到更新时显示原更新提示'
})

watch(availableVersion, version => {
  if (version && !realTargetVersion.value) {
    realTargetVersion.value = version
  }
})

const useCheckedVersion = () => {
  if (!availableVersion.value) {
    message.warning('尚未检查到可用版本')
    return
  }
  realTargetVersion.value = availableVersion.value
}

const startLowSpeedSimulation = () => {
  if (lowSpeedTimer) clearTimeout(lowSpeedTimer)
  simulateProgress(simulatedSource.value, simulatedPercent.value, 40 * 1024)
  message.info('已开始低速模拟，10 秒后将再次上报低速进度')
  lowSpeedTimer = setTimeout(() => {
    simulateProgress(simulatedSource.value, simulatedPercent.value + 1, 40 * 1024)
    lowSpeedTimer = null
  }, 10_000)
}

const runRealCheck = async () => {
  isChecking.value = true
  try {
    await checkUpdate(false, true)
    useCheckedVersion()
  } finally {
    isChecking.value = false
  }
}

const confirmRealDownload = () => {
  if (!realTargetVersion.value) {
    message.warning('请输入目标版本')
    return
  }
  Modal.confirm({
    title: '开始真实更新下载？',
    content: `将从后端下载 ${realTargetVersion.value} 更新包。`,
    okText: '开始下载',
    cancelText: '取消',
    centered: true,
    onOk: () => start(realTargetVersion.value, availableUpdateData.value),
  })
}

const confirmRealCancel = () => {
  Modal.confirm({
    title: '真实取消更新下载？',
    content: '这会停止后台任务并删除未完成的临时文件。',
    okText: '确认取消',
    cancelText: '返回',
    okType: 'danger',
    centered: true,
    onOk: cancel,
  })
}

const confirmRealSwitch = () => {
  Modal.confirm({
    title: '真实切换至 CNB 源？',
    content: '这会停止当前下载、保存更新源并重新开始下载。',
    okText: '切换至 CNB',
    cancelText: '取消',
    centered: true,
    onOk: switchToCnb,
  })
}

const confirmRealInstall = () => {
  Modal.confirm({
    title: '启动真实安装程序？',
    content: '应用可能关闭并启动更新安装程序。',
    okText: '启动安装',
    cancelText: '取消',
    centered: true,
    onOk: install,
  })
}

onUnmounted(() => {
  if (lowSpeedTimer) clearTimeout(lowSpeedTimer)
})
</script>

<style scoped>
.update-download-dev-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header :deep(.ant-typography) {
  margin-bottom: 4px;
}

.summary-row,
.section-alert,
.section-card {
  margin-bottom: 16px;
}

.status-tag {
  margin-top: 8px;
}

.full-width {
  width: 100%;
}
</style>
