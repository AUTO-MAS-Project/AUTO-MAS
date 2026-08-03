<template>
  <section
    class="maafw-project-manager-workspace"
    :class="{ 'manager-scroll-container': scrollContainer }"
  >
    <div v-if="api.capabilities.value?.distributionVersion" class="manager-version">
      <a-tag color="blue">Managed {{ api.capabilities.value.distributionVersion }}</a-tag>
    </div>
    <a-alert
      v-if="api.capabilities.value && !api.capabilities.value.available"
      type="warning"
      show-icon
      message="当前环境未启用 MaaFW 托管资源管理"
      :description="api.capabilities.value.unavailableReason"
    >
      <template #action>
        <a-button size="small" :loading="initialLoading" @click="loadManager">重试</a-button>
      </template>
    </a-alert>

    <a-alert
      v-else-if="pageError"
      type="error"
      show-icon
      message="项目管理数据加载失败"
      :description="pageError"
    >
      <template #action>
        <a-button size="small" :loading="initialLoading" @click="loadManager">重试</a-button>
      </template>
    </a-alert>

    <div v-if="operationProgressVisible" class="operation-progress-panel">
      <div class="progress-heading">
        <div>
          <strong>{{ api.progress.value.stage || '正在处理 MaaFW 资源' }}</strong>
          <p>{{ api.progress.value.message }}</p>
        </div>
        <a-space>
          <a-button
            v-if="progressRecoveryUncertain"
            size="small"
            danger
            @click="confirmReleaseProgressTracking"
          >
            核对状态并解除旧跟踪
          </a-button>
          <a-tag :color="progressTagColor">{{ progressStatusLabel }}</a-tag>
        </a-space>
      </div>
      <a-progress
        :percent="api.progress.value.percent ?? 0"
        :show-info="api.progress.value.percent !== null"
        :status="progressBarStatus"
      />
      <div v-if="progressBytes" class="progress-bytes">{{ progressBytes }}</div>
      <a-collapse v-if="api.progress.value.logs.length" ghost>
        <a-collapse-panel key="logs" header="查看操作日志">
          <pre class="operation-logs">{{ api.progress.value.logs.join('\n') }}</pre>
        </a-collapse-panel>
      </a-collapse>
    </div>

    <div v-if="initialLoading" class="manager-loading">
      <a-spin size="large" tip="正在读取 MaaFW 托管能力与资源" />
    </div>

    <a-tabs v-else-if="api.capabilities.value?.available && binding" v-model:active-key="activeTab">
      <a-tab-pane key="resources" tab="项目与依赖">
        <MaaFWProjectResourcesPanel
          :binding="binding"
          :features="effectiveFeatures"
          :projects="projects"
          :versions="versions"
          :runtimes="runtimes"
          :selected-project-id="selectedProjectId"
          :loading="overviewLoading"
          :versions-loading="versionsLoading"
          :busy="operationRunning"
          @refresh="refreshOverview"
          @select-project="selectProject"
          @switch-version="confirmSwitchVersion"
          @delete-version="confirmDeleteVersion"
          @pin-version="confirmPinVersion"
          @install-runtime="prepareRuntime"
          @delete-runtime="confirmDeleteRuntime"
          @pin-runtime="confirmPinRuntime"
        />
      </a-tab-pane>

      <a-tab-pane key="operations" tab="导入与升级">
        <MaaFWProjectOperationsPanel
          :script-id="scriptId"
          :binding="binding"
          :features="effectiveFeatures"
          :busy="operationRunning"
          :remote-discovery="remoteDiscovery"
          @convert="confirmConvert"
          @local-submit="confirmLocalSubmit"
          @remote-check="checkRemote"
          @remote-submit="confirmRemoteSubmit"
          @apply-plan="confirmApplyPlan"
          @cancel-plan="confirmCancelPlan"
        />
      </a-tab-pane>

      <a-tab-pane
        v-if="effectiveFeatures.garbageCollection !== false"
        key="maintenance"
        tab="空间回收"
      >
        <section class="maintenance-section">
          <div class="section-heading">
            <div>
              <h3>过期资源回收</h3>
              <p>先生成预览；当前版本、固定资源、引用和活动 lease 始终受到保护。</p>
            </div>
          </div>

          <a-form layout="vertical" class="gc-form">
            <a-row :gutter="16">
              <a-col :span="8">
                <a-form-item label="项目范围">
                  <a-select
                    v-model:value="gcForm.projectId"
                    allow-clear
                    :disabled="operationRunning"
                    placeholder="全部托管项目"
                  >
                    <a-select-option
                      v-for="project in projects"
                      :key="project.projectId"
                      :value="project.projectId"
                    >
                      {{ project.projectId }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="宽限期（天）">
                  <a-input-number
                    v-model:value="gcForm.graceDays"
                    :min="0"
                    :max="3650"
                    :disabled="operationRunning"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="每个项目 / 运行时保留最新数量">
                  <a-input-number
                    v-model:value="gcForm.keepLatest"
                    :min="0"
                    :max="100"
                    :disabled="operationRunning"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-space>
              <a-button :loading="operationRunning" @click="previewGarbageCollection">
                预览回收
              </a-button>
              <a-button
                danger
                :disabled="operationRunning || !gcPreview"
                @click="confirmGarbageCollection"
              >
                执行预览中的回收
              </a-button>
            </a-space>
          </a-form>

          <a-alert
            v-if="gcPreview"
            type="info"
            show-icon
            message="空间回收预览已生成"
            :description="gcPreviewSummary"
          />

          <a-collapse v-if="gcPreview" ghost>
            <a-collapse-panel key="gc-detail" header="查看完整回收清单">
              <pre class="gc-detail">{{ JSON.stringify(gcPreview, null, 2) }}</pre>
            </a-collapse-panel>
          </a-collapse>
        </section>
      </a-tab-pane>
    </a-tabs>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { message, Modal, type ModalFuncProps } from 'ant-design-vue'
import {
  useMaaFWManagedApi,
  type MaaFWManagedBinding,
  type MaaFWManagedFeatures,
  type MaaFWManagedGarbageCollectionResult,
  type MaaFWManagedLocalSourceInput,
  type MaaFWManagedProjectSummary,
  type MaaFWManagedProjectVersion,
  type MaaFWManagedRemoteDiscovery,
  type MaaFWManagedRemoteSourceInput,
  type MaaFWManagedRuntime,
} from '@/composables/useMaaFWManagedApi'
import MaaFWProjectOperationsPanel from './MaaFWProjectOperationsPanel.vue'
import MaaFWProjectResourcesPanel from './MaaFWProjectResourcesPanel.vue'

defineOptions({ name: 'MaaFWProjectManagerWorkspace' })

const MANAGER_CONFIRM_Z_INDEX = 950

const props = withDefaults(
  defineProps<{
    scriptId: string
    scrollContainer?: boolean
  }>(),
  {
    scrollContainer: false,
  }
)

const emit = defineEmits<{
  converted: [scriptId: string]
  refreshed: []
  'busy-change': [busy: boolean]
  'operation-change': [running: boolean]
}>()

const api = useMaaFWManagedApi()
type ConfirmHandle = ReturnType<typeof Modal.confirm>
const activeConfirmHandles = new Set<ConfirmHandle>()
let disposed = false
const initialLoading = ref(false)
const overviewLoading = ref(false)
const versionsLoading = ref(false)
const pageError = ref('')
const activeTab = ref<'resources' | 'operations' | 'maintenance'>('resources')
const binding = ref<MaaFWManagedBinding | null>(null)
const projects = ref<MaaFWManagedProjectSummary[]>([])
const versions = ref<MaaFWManagedProjectVersion[]>([])
const runtimes = ref<MaaFWManagedRuntime[]>([])
const selectedProjectId = ref('')
const remoteDiscovery = ref<MaaFWManagedRemoteDiscovery | null>(null)
const gcPreview = ref<MaaFWManagedGarbageCollectionResult | null>(null)
const gcPreviewInput = ref<{
  projectId?: string
  graceDays: number
  keepLatest: number
} | null>(null)
const mutationFinalizing = ref(false)
const gcForm = reactive({
  projectId: '',
  graceDays: 30,
  keepLatest: 2,
})
let versionsRequestSequence = 0
let overviewRefreshPromise: Promise<boolean> | null = null
let terminalReconciliationPromise: Promise<void> | null = null
let terminalRefreshPending = false
let terminalReconciliationGeneration = 0

const operationRunning = computed(
  () =>
    initialLoading.value ||
    overviewLoading.value ||
    versionsLoading.value ||
    mutationFinalizing.value ||
    api.loading.value ||
    api.progress.value.status === 'running'
)
const mutationRunning = computed(
  () => api.progress.value.status === 'running' || mutationFinalizing.value
)

const effectiveFeatures = computed<MaaFWManagedFeatures>(() => {
  const features = api.capabilities.value?.features
    ? { ...api.capabilities.value.features }
    : {
        inPlaceConversion: false,
        singleEntry: false,
        conversionRecovery: false,
        projectOverview: false,
        localImport: false,
        remoteImport: false,
        upgradePlans: false,
        runtimeManagement: false,
        pinning: false,
        garbageCollection: false,
        operationProgress: false,
      }
  if (binding.value && !binding.value.managed && binding.value.scriptType !== 'MaaFW') {
    features.inPlaceConversion = false
  }
  return features
})

const operationProgressVisible = computed(() => api.progress.value.status !== 'idle')
const progressRecoveryUncertain = computed(
  () => api.progress.value.status === 'running' && api.progress.value.stage === '正在确认进度记录'
)
const progressTagColor = computed(() => {
  if (api.progress.value.status === 'success') return 'green'
  if (api.progress.value.status === 'error') return 'red'
  if (api.progress.value.status === 'unknown') return 'orange'
  return 'blue'
})
const progressStatusLabel = computed(() => {
  if (api.progress.value.status === 'success') return '已完成'
  if (api.progress.value.status === 'error') return '失败'
  if (api.progress.value.status === 'unknown') return '结果待核对'
  return '处理中'
})
const progressBarStatus = computed<'active' | 'success' | 'exception' | 'normal'>(() => {
  if (api.progress.value.status === 'success') return 'success'
  if (api.progress.value.status === 'error') return 'exception'
  if (api.progress.value.status === 'unknown') return 'normal'
  return 'active'
})
const progressBytes = computed(() => {
  const downloaded = api.progress.value.downloadedBytes
  const total = api.progress.value.totalBytes
  if (downloaded === null && total === null) return ''
  return `${formatBytes(downloaded)} / ${formatBytes(total)}`
})

const gcPreviewSummary = computed(() => {
  if (!gcPreview.value) return ''
  const projectStore = asRecord(gcPreview.value.projectStore)
  const runtimePool = asRecord(gcPreview.value.runtimePool)
  const projectCandidates = Array.isArray(projectStore.candidates)
    ? projectStore.candidates.length
    : 0
  const runtimeCandidates = Array.isArray(runtimePool.candidates)
    ? runtimePool.candidates.length
    : 0
  const checkoutGarbageCollection = asRecord(projectStore.checkoutGarbageCollection)
  const checkoutCandidates = Array.isArray(checkoutGarbageCollection.candidates)
    ? checkoutGarbageCollection.candidates.length
    : 0
  const reclaimed =
    numberOrZero(projectStore.reclaimedBytes) +
    numberOrZero(runtimePool.reclaimedBytes) +
    numberOrZero(checkoutGarbageCollection.reclaimedBytes)
  return `候选项目版本 ${projectCandidates} 个，脱壳目录 ${checkoutCandidates} 个，共享运行时 ${runtimeCandidates} 个，预计释放 ${formatBytes(reclaimed)}`
})

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}

const numberOrZero = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? value : 0

const formatBytes = (value: number | null) => {
  if (value === null || !Number.isFinite(value)) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(2)} GB`
}

const reportFailure = (caught: unknown, fallback: string) => {
  const reason = caught instanceof Error ? caught.message : fallback
  pageError.value = reason
  message.error(reason)
}

const showManagedConfirm = (config: ModalFuncProps) => {
  const confirmedScriptId = props.scriptId
  let handle!: ConfirmHandle
  handle = Modal.confirm({
    ...config,
    zIndex: MANAGER_CONFIRM_Z_INDEX,
    onOk: (...args: unknown[]) => {
      if (disposed || props.scriptId !== confirmedScriptId) {
        message.warning('项目上下文已改变，本次操作已取消')
        return
      }
      return config.onOk?.(...args)
    },
    afterClose: () => {
      activeConfirmHandles.delete(handle)
      config.afterClose?.()
    },
  })
  activeConfirmHandles.add(handle)
}

const loadManager = async () => {
  initialLoading.value = true
  pageError.value = ''
  remoteDiscovery.value = null
  gcPreview.value = null
  gcPreviewInput.value = null
  api.resetProgress()
  try {
    const wasFinalizing = mutationFinalizing.value
    const previousManaged = binding.value?.managed
    const capabilities = await api.getCapabilities()
    if (disposed || !capabilities.available) return
    await api.resumeProgress(props.scriptId)
    if (disposed) return
    const overview = await api.getOverview(props.scriptId)
    if (disposed) return
    binding.value = overview.binding
    projects.value = overview.projects
    runtimes.value = overview.runtimes
    activeTab.value = overview.binding.managed ? 'resources' : 'operations'
    if (previousManaged === false && overview.binding.managed) emit('converted', props.scriptId)
    const preferredProject = overview.binding.projectId || overview.projects[0]?.projectId || ''
    if (preferredProject) {
      const versionsLoaded = await selectProject(preferredProject)
      if (!versionsLoaded) return
    } else {
      selectedProjectId.value = ''
      versions.value = []
    }
    if (wasFinalizing && !terminalRefreshPending) emit('refreshed')
    if (!terminalRefreshPending) mutationFinalizing.value = false
  } catch (caught) {
    if (disposed) return
    reportFailure(caught, '读取 MaaFW 项目管理数据失败')
  } finally {
    initialLoading.value = false
    if (terminalRefreshPending) {
      terminalRefreshPending = false
      queueTerminalReconciliation()
    }
  }
}

watch(
  () => props.scriptId,
  () => void loadManager(),
  { immediate: true }
)

watch(operationRunning, busy => emit('busy-change', busy), { immediate: true })

watch(
  () => api.progress.value.status,
  (status, previousStatus) => {
    if (
      previousStatus === 'running' &&
      (status === 'success' || status === 'error' || status === 'unknown')
    ) {
      terminalReconciliationGeneration += 1
      mutationFinalizing.value = true
      if (initialLoading.value) {
        terminalRefreshPending = true
        return
      }
      queueTerminalReconciliation()
    }
  },
  { flush: 'sync' }
)

watch(mutationRunning, running => emit('operation-change', running), { immediate: true })

watch(
  () => [gcForm.projectId, gcForm.graceDays, gcForm.keepLatest] as const,
  () => {
    gcPreview.value = null
    gcPreviewInput.value = null
  }
)

const finalizeTerminalReconciliation = (refreshGeneration: number) => {
  if (
    !mutationFinalizing.value ||
    refreshGeneration !== terminalReconciliationGeneration ||
    !['success', 'error', 'unknown'].includes(api.progress.value.status)
  ) {
    return
  }
  if (api.progress.value.status === 'unknown') {
    api.progress.value = {
      ...api.progress.value,
      stage: '资源状态已核对，操作结果未知',
      message: '后端旧操作记录无法恢复；当前资源状态已经刷新，请根据页面结果决定后续操作',
    }
  } else if (
    api.progress.value.status === 'success' &&
    api.progress.value.stage === '服务端已确认无活跃操作'
  ) {
    api.progress.value = {
      ...api.progress.value,
      stage: '资源状态已核对',
      message: '服务端已无活跃操作，当前项目与运行时状态已经刷新并安全解锁',
    }
  }
  mutationFinalizing.value = false
}

const refreshOverview = () => {
  if (overviewRefreshPromise) return overviewRefreshPromise
  if (disposed || !api.capabilities.value?.available) return Promise.resolve(false)
  const refreshGeneration = terminalReconciliationGeneration
  overviewRefreshPromise = (async () => {
    overviewLoading.value = true
    pageError.value = ''
    try {
      const overview = await api.getOverview(props.scriptId)
      if (disposed) return false
      const convertedToManaged = binding.value?.managed === false && overview.binding.managed
      binding.value = overview.binding
      projects.value = overview.projects
      runtimes.value = overview.runtimes
      if (convertedToManaged) {
        activeTab.value = 'resources'
        emit('converted', props.scriptId)
      }
      const selectedProjectStillExists = overview.projects.some(
        project => project.projectId === selectedProjectId.value
      )
      const projectId =
        overview.binding.projectId ||
        (selectedProjectStillExists ? selectedProjectId.value : '') ||
        overview.projects[0]?.projectId ||
        ''
      if (projectId) {
        const versionsLoaded = await selectProject(projectId, true)
        if (disposed || !versionsLoaded) return false
      } else {
        selectedProjectId.value = ''
        versions.value = []
      }
      emit('refreshed')
      finalizeTerminalReconciliation(refreshGeneration)
      return true
    } catch (caught) {
      if (disposed) return false
      reportFailure(caught, '刷新 MaaFW 项目管理数据失败')
      return false
    } finally {
      overviewLoading.value = false
    }
  })().finally(() => {
    overviewRefreshPromise = null
  })
  return overviewRefreshPromise
}

const queueTerminalReconciliation = () => {
  if (terminalReconciliationPromise) return
  terminalReconciliationPromise = (async () => {
    const refreshStartedBeforeTerminal = overviewRefreshPromise
    if (refreshStartedBeforeTerminal) {
      await refreshStartedBeforeTerminal
      if (!mutationFinalizing.value) return
    }
    if (disposed) return
    await refreshOverview()
  })().finally(() => {
    terminalReconciliationPromise = null
  })
}

const selectProject = async (projectId: string, force = false): Promise<boolean> => {
  if (!projectId || (!force && projectId === selectedProjectId.value && versions.value.length)) {
    return true
  }
  const requestSequence = ++versionsRequestSequence
  selectedProjectId.value = projectId
  versionsLoading.value = true
  try {
    const nextVersions = await api.listVersions(props.scriptId, projectId)
    if (
      disposed ||
      requestSequence !== versionsRequestSequence ||
      selectedProjectId.value !== projectId
    ) {
      return false
    }
    versions.value = nextVersions
    return true
  } catch (caught) {
    if (
      disposed ||
      requestSequence !== versionsRequestSequence ||
      selectedProjectId.value !== projectId
    ) {
      return false
    }
    versions.value = []
    reportFailure(caught, `读取项目 ${projectId} 的版本失败`)
    return false
  } finally {
    if (requestSequence === versionsRequestSequence) {
      versionsLoading.value = false
    }
  }
}

const runAndRefresh = async <T,>(
  operation: () => Promise<T>,
  successText: string
): Promise<T | null> => {
  pageError.value = ''
  try {
    const result = await operation()
    if (disposed) return null
    if (result === undefined && api.progress.value.status === 'success') {
      message.warning('服务端确认操作已完成，但原请求响应丢失；正在刷新资源状态，请勿重复提交')
      await refreshOverview()
      return null
    }
    if (result === undefined && api.progress.value.status === 'unknown') {
      message.warning('连接中断且后端已重启，操作结果待核对；正在刷新资源状态，请勿重复提交')
      await refreshOverview()
      return null
    }
    message.success(successText)
    await refreshOverview()
    return result
  } catch (caught) {
    if (disposed) return null
    if (api.progress.value.status === 'running') {
      pageError.value = ''
      message.warning('请求连接已中断，后台操作状态仍在确认中；恢复终态前不会解锁新操作')
      return null
    }
    if (api.progress.value.status === 'success') {
      message.warning('后台操作已完成，但原请求响应中断；已按权威状态刷新资源')
      await refreshOverview()
      return null
    }
    if (api.progress.value.status === 'unknown') {
      message.warning('连接中断且后端已无原操作记录；正在核对资源状态，请勿重复提交')
      await refreshOverview()
      return null
    }
    reportFailure(caught, 'MaaFW 托管资源操作失败')
    return null
  }
}

const confirmConvert = (input: {
  projectId?: string
  version?: string
  runtimeConstraint?: string
}) => {
  showManagedConfirm({
    title: '转换为托管 MaaFW 项目？',
    content:
      '后端会从当前项目路径导入不可变资源，并保留此脚本 ID、全部用户和任务关联。转换失败时不会报告为已完成。',
    okText: '确认转换',
    cancelText: '取消',
    async onOk() {
      const result = await runAndRefresh(
        () => api.convert({ scriptId: props.scriptId, ...input }),
        '已转换为托管 MaaFW 项目'
      )
      if (result && (result.converted || result.idempotent)) {
        activeTab.value = 'resources'
      }
    },
  })
}

const confirmLocalSubmit = (mode: 'import' | 'upgrade', input: MaaFWManagedLocalSourceInput) => {
  showManagedConfirm({
    title: mode === 'upgrade' ? '导入资源并生成升级计划？' : '导入首个托管资源版本？',
    content:
      mode === 'upgrade'
        ? '新版本会以非活动状态导入；确认计划前，当前版本与配置继续生效。'
        : '目录或 ZIP 会复制到 Project Store，后续运行不再依赖原始来源路径。',
    okText: '继续',
    cancelText: '取消',
    async onOk() {
      if (mode === 'upgrade') {
        const result = await runAndRefresh(() => api.upgradeLocal(input), '升级计划已生成')
        if (result) activeTab.value = 'operations'
        return
      }
      await runAndRefresh(() => api.importLocal(input), '托管资源已导入')
    },
  })
}

const checkRemote = async (input: MaaFWManagedRemoteSourceInput) => {
  remoteDiscovery.value = null
  try {
    const discovery = await api.checkRemote(input)
    if (disposed) return
    if (!discovery) {
      message.warning(
        api.progress.value.status === 'unknown'
          ? '连接中断且后端已重启，未能恢复远程检查结果；请重新检查'
          : '远程资源检查已完成，但原请求响应中断；请重新检查以读取最新结果'
      )
      return
    }
    remoteDiscovery.value = discovery
    message.info(remoteDiscovery.value.message || '远程资源检查完成')
  } catch (caught) {
    if (disposed) return
    reportFailure(caught, '检查远程 MaaFW 资源失败')
  }
}

const confirmRemoteSubmit = (mode: 'import' | 'upgrade', input: MaaFWManagedRemoteSourceInput) => {
  showManagedConfirm({
    title: mode === 'upgrade' ? '下载资源并生成升级计划？' : '下载并导入托管资源？',
    content: '只会使用能力探测返回的可安装候选；无下载地址的远程版本不会进入安装。',
    okText: '开始下载',
    cancelText: '取消',
    async onOk() {
      const result = await runAndRefresh(
        () => (mode === 'upgrade' ? api.upgradeRemote(input) : api.importRemote(input)),
        mode === 'upgrade' ? '远程升级计划已生成' : '远程资源已导入'
      )
      if (result) remoteDiscovery.value = null
    },
  })
}

const confirmSwitchVersion = (version: MaaFWManagedProjectVersion) => {
  if (!binding.value?.projectId || version.projectId !== binding.value.projectId) {
    message.warning('只能在当前绑定项目内切换版本')
    return
  }
  showManagedConfirm({
    title: `切换到 ${version.version}？`,
    content: '此操作只生成配置迁移计划；再次确认并通过 CAS 校验后才会切换。',
    okText: '生成计划',
    cancelText: '取消',
    async onOk() {
      const result = await runAndRefresh(
        () => api.switchVersion(props.scriptId, version.projectId, version.version),
        '版本切换计划已生成'
      )
      if (result) activeTab.value = 'operations'
    },
  })
}

const confirmApplyPlan = () => {
  const plan = binding.value?.pendingPlan
  if (plan?.state !== 'ready' || !plan.readyToApply || !plan.confirmationToken) return
  showManagedConfirm({
    title: '应用升级计划并切换资源？',
    content: `将应用计划 ${plan.planId}，确认令牌为 ${plan.confirmationToken}。应用前后端会重新校验脚本和全部用户配置。`,
    okText: '应用并切换',
    cancelText: '取消',
    async onOk() {
      await runAndRefresh(
        () => api.applyUpgrade(props.scriptId, plan.planId, plan.confirmationToken),
        '升级计划已应用，项目版本已切换'
      )
    },
  })
}

const confirmCancelPlan = () => {
  showManagedConfirm({
    title: '取消待确认升级？',
    content: '当前生效版本不会改变；待确认版本的临时引用会由后端安全释放。',
    okText: '确认取消',
    cancelText: '返回',
    async onOk() {
      await runAndRefresh(() => api.cancelUpgrade(props.scriptId), '待确认升级已取消')
    },
  })
}

const prepareRuntime = async () => {
  const current = binding.value
  if (!current?.projectId || !current.version) return
  await runAndRefresh(
    () =>
      api.installRuntime(
        props.scriptId,
        current.projectId,
        current.version,
        current.runtimeConstraint || undefined
      ),
    '共享 MaaFW 运行时已就绪'
  )
}

const confirmDeleteVersion = (version: MaaFWManagedProjectVersion) => {
  showManagedConfirm({
    title: `删除 ${version.projectId}@${version.version}？`,
    content: '删除不可恢复；存在当前指针、引用、固定标记或活动 lease 时，后端会拒绝操作。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await runAndRefresh(
        () => api.deleteVersion(props.scriptId, version.projectId, version.version),
        `已删除 ${version.projectId}@${version.version}`
      )
    },
  })
}

const confirmDeleteRuntime = (runtime: MaaFWManagedRuntime) => {
  showManagedConfirm({
    title: `删除共享运行时 ${runtime.runtimeId}？`,
    content: '删除不可恢复；存在引用、固定标记或活动 lease 时，后端会拒绝操作。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await runAndRefresh(
        () => api.deleteRuntime(props.scriptId, runtime.runtimeId),
        `已删除共享运行时 ${runtime.runtimeId}`
      )
    },
  })
}

const confirmPinVersion = (version: MaaFWManagedProjectVersion, pinned: boolean) => {
  const action = () =>
    runAndRefresh(
      () =>
        api.pin(props.scriptId, pinned, {
          projectId: version.projectId,
          version: version.version,
        }),
      pinned ? '项目版本已固定' : '项目版本已取消固定'
    )
  if (pinned) {
    void action()
    return
  }
  showManagedConfirm({
    title: `取消固定 ${version.projectId}@${version.version}？`,
    content: '取消固定后，该版本可能在满足宽限期和引用条件时被 GC 回收。',
    okText: '取消固定',
    cancelText: '返回',
    onOk: action,
  })
}

const confirmPinRuntime = (runtime: MaaFWManagedRuntime, pinned: boolean) => {
  const action = () =>
    runAndRefresh(
      () => api.pin(props.scriptId, pinned, { runtimeId: runtime.runtimeId }),
      pinned ? '共享运行时已固定' : '共享运行时已取消固定'
    )
  if (pinned) {
    void action()
    return
  }
  showManagedConfirm({
    title: `取消固定 ${runtime.runtimeId}？`,
    content: '取消固定后，该运行时可能在满足宽限期和引用条件时被 GC 回收。',
    okText: '取消固定',
    cancelText: '返回',
    onOk: action,
  })
}

const previewGarbageCollection = async () => {
  const input = {
    projectId: gcForm.projectId || undefined,
    graceDays: gcForm.graceDays,
    keepLatest: gcForm.keepLatest,
  }
  const preview = await runAndRefresh(
    () =>
      api.collectGarbage(props.scriptId, {
        dryRun: true,
        ...input,
      }),
    '空间回收预览已生成'
  )
  if (preview) {
    gcPreview.value = preview
    gcPreviewInput.value = input
  }
}

const confirmGarbageCollection = () => {
  const input = gcPreviewInput.value
  if (!gcPreview.value || !input) return
  showManagedConfirm({
    title: '执行空间回收？',
    content: `${gcPreviewSummary.value}。实际结果仍以执行时的引用和 lease 复核为准。`,
    okText: '确认回收',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      const result = await runAndRefresh(
        () =>
          api.collectGarbage(props.scriptId, {
            dryRun: false,
            ...input,
          }),
        '过期项目与运行时回收完成'
      )
      if (result) {
        gcPreview.value = null
        gcPreviewInput.value = null
      }
    },
  })
}

const confirmReleaseProgressTracking = () => {
  const operationId = api.progress.value.operationId
  if (!operationId || api.progress.value.status !== 'running') return
  showManagedConfirm({
    title: '核对当前资源并解除旧操作跟踪？',
    content:
      '当前无法从进度端点确认旧操作是否仍在执行。系统会先重新读取脚本绑定、项目版本和运行时；仅核对成功后解除前端锁定。解除后请勿立即重复相同的删除、升级或回收操作。',
    okText: '核对并解除',
    cancelText: '继续等待',
    async onOk() {
      if (api.progress.value.operationId !== operationId || !progressRecoveryUncertain.value) {
        message.info('操作进度已经恢复或发生变化，无需解除旧跟踪')
        return
      }
      const refreshed = await refreshOverview()
      if (!refreshed) throw new Error('当前资源状态核对失败，请恢复连接后重试')
      if (api.progress.value.operationId !== operationId || !progressRecoveryUncertain.value) {
        message.info('核对期间操作进度已经恢复或发生变化，已继续保持跟踪')
        return
      }
      if (api.releaseProgressTracking(props.scriptId, operationId)) {
        message.warning('已解除旧操作的前端进度跟踪；执行新的资源操作前请确认当前状态')
      }
    },
  })
}

onBeforeUnmount(() => {
  disposed = true
  emit('busy-change', false)
  emit('operation-change', false)
  activeConfirmHandles.forEach(handle => handle.destroy())
  activeConfirmHandles.clear()
  api.dispose()
})
</script>

<style scoped>
.manager-version {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.manager-scroll-container {
  max-height: min(760px, calc(100vh - 176px));
  min-height: min(360px, calc(100vh - 176px));
  padding: 24px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.maafw-project-manager-workspace:not(.manager-scroll-container) {
  min-height: 360px;
}

.manager-loading {
  display: flex;
  min-height: 360px;
  align-items: center;
  justify-content: center;
}

.operation-progress-panel {
  margin-bottom: 16px;
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.progress-heading,
.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.progress-heading p {
  margin: 4px 0 8px;
  color: var(--ant-color-text-secondary);
}

.progress-bytes {
  margin-top: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.operation-logs,
.gc-detail {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  color: var(--ant-color-text);
  background: var(--ant-color-fill-tertiary);
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
}

.maintenance-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-heading h3 {
  margin: 0 0 4px;
  color: var(--ant-color-text);
  font-size: 16px;
}

.section-heading p {
  margin: 0;
  color: var(--ant-color-text-secondary);
}

.gc-form {
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}
</style>
