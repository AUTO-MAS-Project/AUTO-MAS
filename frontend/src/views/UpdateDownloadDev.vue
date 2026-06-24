<template>
  <div class="update-download-dev-page">
    <a-flex justify="space-between" align="center" class="page-header">
      <div>
        <a-typography-title :level="3">更新下载测试</a-typography-title>
        <a-typography-text type="secondary">
          仅开发模式可见。优先使用安全模拟区验证界面状态。
        </a-typography-text>
      </div>
      <a-space>
        <a-tag :color="statusColor">{{ statusLabel }}</a-tag>
        <a-button @click="open">恢复下载弹窗</a-button>
        <a-button @click="resetSimulation">重置状态</a-button>
      </a-space>
    </a-flex>

    <a-alert
      type="info"
      show-icon
      message="安全模拟不会访问后端，也不会下载或安装文件。"
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
            <a-button @click="startLowSpeedSimulation">模拟 GitHub 持续低速</a-button>
          </a-space>
        </a-form>
      </a-space>
    </a-card>

    <a-alert
      type="warning"
      show-icon
      message="以下操作会调用真实后端，可能下载文件、修改更新源或启动安装程序。"
      class="section-alert"
    />

    <a-card title="真实后端操作" class="section-card">
      <a-space direction="vertical" size="middle" class="full-width">
        <a-space wrap>
          <a-button :loading="isChecking" @click="runRealCheck">真实检查更新</a-button>
          <a-button type="primary" @click="confirmRealDownload">开始真实下载</a-button>
          <a-button danger :disabled="status !== 'downloading'" @click="confirmRealCancel">
            真实取消下载
          </a-button>
          <a-button
            :disabled="status !== 'downloading' || source !== 'GitHub'"
            @click="confirmRealSwitch"
          >
            真实切换 CNB
          </a-button>
          <a-button :disabled="status !== 'completed'" @click="confirmRealInstall">
            启动真实安装
          </a-button>
        </a-space>

        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="版本">
            {{ latestVersion || availableVersion || '尚未检查' }}
          </a-descriptions-item>
          <a-descriptions-item label="来源">{{ sourceLabel || '尚无来源' }}</a-descriptions-item>
          <a-descriptions-item label="进度">
            {{ progressPercent.toFixed(1) }}%
          </a-descriptions-item>
          <a-descriptions-item label="失败原因">
            {{ failureReason || '无' }}
          </a-descriptions-item>
        </a-descriptions>
      </a-space>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { useUpdateChecker, useUpdateModal } from '@/composables/useUpdateChecker'
import { useUpdateDownload } from '@/composables/useUpdateDownload'
import { useUpdateDownloadDevtools } from '@/composables/updateDownloadDevtools'

type SimulatedSource = 'GitHub' | 'CNB' | 'MirrorChyan' | 'AutoSite'

const {
  status,
  source,
  sourceLabel,
  progressPercent,
  failureReason,
  latestVersion,
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

const startLowSpeedSimulation = () => {
  if (lowSpeedTimer) clearTimeout(lowSpeedTimer)
  simulateProgress('GitHub', simulatedPercent.value, 40 * 1024)
  message.info('已开始低速模拟，10 秒后将再次上报低速进度')
  lowSpeedTimer = setTimeout(() => {
    simulateProgress('GitHub', simulatedPercent.value + 1, 40 * 1024)
    lowSpeedTimer = null
  }, 10_000)
}

const runRealCheck = async () => {
  isChecking.value = true
  try {
    await checkUpdate(false, true)
  } finally {
    isChecking.value = false
  }
}

const confirmRealDownload = () => {
  const version = availableVersion.value || latestVersion.value
  if (!version) {
    message.warning('请先执行真实检查更新')
    return
  }
  Modal.confirm({
    title: '开始真实更新下载？',
    content: `将从后端下载 ${version} 更新包。`,
    okText: '开始下载',
    cancelText: '取消',
    centered: true,
    onOk: () => start(version, availableUpdateData.value),
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
    content: '这会停止当前 GitHub 下载、保存更新源并重新开始下载。',
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

.section-alert {
  margin-bottom: 16px;
}

.section-card {
  margin-bottom: 24px;
}

.full-width {
  width: 100%;
}
</style>
