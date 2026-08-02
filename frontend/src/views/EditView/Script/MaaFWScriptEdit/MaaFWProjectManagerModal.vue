<template>
  <a-modal
    :open="open"
    width="1180px"
    :footer="null"
    :mask-closable="false"
    :keyboard="!operationRunning"
    :z-index="900"
    :destroy-on-close="true"
    :body-style="{ padding: '0', overflow: 'hidden' }"
    class="maafw-project-manager-modal"
    @cancel="handleClose"
  >
    <template #title>
      <div class="modal-title">
        <span>MaaFW 项目管理</span>
        <a-tag v-if="api.capabilities.value?.distributionVersion" color="blue">
          Managed {{ api.capabilities.value.distributionVersion }}
        </a-tag>
      </div>
    </template>

    <div class="manager-scroll-container">
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
          <a-tag :color="progressTagColor">{{ progressStatusLabel }}</a-tag>
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

      <a-tabs
        v-else-if="api.capabilities.value?.available && binding"
        v-model:active-key="activeTab"
      >
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
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
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

const props = defineProps<{
  open: boolean
  scriptId: string
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  converted: [scriptId: string]
  refreshed: []
}>()

const api = useMaaFWManagedApi()
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
const gcForm = reactive({
  projectId: '',
  graceDays: 30,
  keepLatest: 2,
})
let versionsRequestSequence = 0

const operationRunning = computed(
  () => api.loading.value || api.progress.value.status === 'running'
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
const progressTagColor = computed(() => {
  if (api.progress.value.status === 'success') return 'green'
  if (api.progress.value.status === 'error') return 'red'
  return 'blue'
})
const progressStatusLabel = computed(() => {
  if (api.progress.value.status === 'success') return '已完成'
  if (api.progress.value.status === 'error') return '失败'
  return '处理中'
})
const progressBarStatus = computed<'active' | 'success' | 'exception'>(() => {
  if (api.progress.value.status === 'success') return 'success'
  if (api.progress.value.status === 'error') return 'exception'
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
  const reclaimed =
    numberOrZero(projectStore.reclaimedBytes) + numberOrZero(runtimePool.reclaimedBytes)
  return `候选项目版本 ${projectCandidates} 个，共享运行时 ${runtimeCandidates} 个，预计释放 ${formatBytes(reclaimed)}`
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

const loadManager = async () => {
  initialLoading.value = true
  pageError.value = ''
  remoteDiscovery.value = null
  gcPreview.value = null
  gcPreviewInput.value = null
  api.resetProgress()
  try {
    const capabilities = await api.getCapabilities()
    if (!capabilities.available) return
    const overview = await api.getOverview(props.scriptId)
    binding.value = overview.binding
    projects.value = overview.projects
    runtimes.value = overview.runtimes
    activeTab.value = overview.binding.managed ? 'resources' : 'operations'
    const preferredProject = overview.binding.projectId || overview.projects[0]?.projectId || ''
    if (preferredProject) await selectProject(preferredProject)
  } catch (caught) {
    reportFailure(caught, '读取 MaaFW 项目管理数据失败')
  } finally {
    initialLoading.value = false
  }
}

watch(
  () => [props.open, props.scriptId] as const,
  ([open]) => {
    if (open) void loadManager()
  },
  { immediate: true }
)

watch(
  () => [gcForm.projectId, gcForm.graceDays, gcForm.keepLatest] as const,
  () => {
    gcPreview.value = null
    gcPreviewInput.value = null
  }
)

const refreshOverview = async () => {
  if (!api.capabilities.value?.available) return
  overviewLoading.value = true
  pageError.value = ''
  try {
    const overview = await api.getOverview(props.scriptId)
    binding.value = overview.binding
    projects.value = overview.projects
    runtimes.value = overview.runtimes
    const projectId =
      overview.binding.projectId || selectedProjectId.value || overview.projects[0]?.projectId || ''
    if (projectId) await selectProject(projectId, true)
    emit('refreshed')
  } catch (caught) {
    reportFailure(caught, '刷新 MaaFW 项目管理数据失败')
  } finally {
    overviewLoading.value = false
  }
}

const selectProject = async (projectId: string, force = false) => {
  if (!projectId || (!force && projectId === selectedProjectId.value && versions.value.length)) {
    return
  }
  const requestSequence = ++versionsRequestSequence
  selectedProjectId.value = projectId
  versionsLoading.value = true
  try {
    const nextVersions = await api.listVersions(props.scriptId, projectId)
    if (requestSequence !== versionsRequestSequence || selectedProjectId.value !== projectId) {
      return
    }
    versions.value = nextVersions
  } catch (caught) {
    if (requestSequence !== versionsRequestSequence || selectedProjectId.value !== projectId) {
      return
    }
    versions.value = []
    reportFailure(caught, `读取项目 ${projectId} 的版本失败`)
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
    message.success(successText)
    await refreshOverview()
    return result
  } catch (caught) {
    reportFailure(caught, 'MaaFW 托管资源操作失败')
    return null
  }
}

const confirmConvert = (input: {
  projectId?: string
  version?: string
  runtimeConstraint?: string
}) => {
  Modal.confirm({
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
        emit('converted', props.scriptId)
      }
    },
  })
}

const confirmLocalSubmit = (mode: 'import' | 'upgrade', input: MaaFWManagedLocalSourceInput) => {
  Modal.confirm({
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
  try {
    remoteDiscovery.value = await api.checkRemote(input)
    message.info(remoteDiscovery.value.message || '远程资源检查完成')
  } catch (caught) {
    reportFailure(caught, '检查远程 MaaFW 资源失败')
  }
}

const confirmRemoteSubmit = (mode: 'import' | 'upgrade', input: MaaFWManagedRemoteSourceInput) => {
  Modal.confirm({
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
  Modal.confirm({
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
  Modal.confirm({
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
  Modal.confirm({
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
  Modal.confirm({
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
  Modal.confirm({
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
  Modal.confirm({
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
  Modal.confirm({
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
  Modal.confirm({
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

const handleClose = () => {
  if (!operationRunning.value) {
    emit('update:open', false)
    return
  }
  Modal.confirm({
    title: '操作仍在进行',
    content: '关闭窗口不会取消后端操作。重新打开后请刷新资源状态。',
    okText: '仍然关闭',
    cancelText: '继续查看',
    onOk: () => emit('update:open', false),
  })
}

onBeforeUnmount(() => api.dispose())
</script>

<style scoped>
.modal-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.manager-scroll-container {
  max-height: min(760px, calc(100vh - 176px));
  min-height: min(360px, calc(100vh - 176px));
  padding: 24px;
  overflow-y: auto;
  overscroll-behavior: contain;
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
