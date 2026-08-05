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

    <a-alert
      v-if="api.capabilities.value?.available && !safeMutationAvailable"
      class="manager-readonly-alert"
      type="warning"
      show-icon
      message="当前 Managed 插件仅允许只读查看"
      :description="mutationUnavailableReason"
    />

    <div v-if="operationProgressVisible" class="operation-progress-panel">
      <div class="progress-heading">
        <div>
          <strong>{{ progressStageLabel }}</strong>
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
        <a-collapse-panel key="logs" header="查看操作过程">
          <ol class="operation-logs" aria-label="MaaFW 项目操作过程">
            <li v-for="(line, index) in api.progress.value.logs" :key="`${index}-${line}`">
              <span class="operation-log-index">{{ index + 1 }}</span>
              <span>{{ line }}</span>
            </li>
          </ol>
        </a-collapse-panel>
      </a-collapse>
    </div>

    <a-alert
      v-if="conversionSuccess"
      class="conversion-success-alert"
      type="success"
      show-icon
      message="转换完成：资源已复制到托管存储，原目录仍保留"
    >
      <template #description>
        <div class="conversion-success-description">
          <span>{{ conversionSourcePathDescription }}</span>
          <a-space v-if="conversionOriginalPath" class="conversion-source-path">
            <a-typography-text code>{{ conversionOriginalPath }}</a-typography-text>
            <a-button size="small" @click="copyConversionOriginalPath">复制原目录路径</a-button>
          </a-space>
          <span v-else class="conversion-source-path-missing">原目录路径暂未读取到。</span>
        </div>
      </template>
    </a-alert>

    <div v-if="initialLoading" class="manager-loading">
      <a-spin size="large" tip="正在读取 MaaFW 托管能力与资源" />
    </div>

    <a-card
      v-if="
        !initialLoading &&
        globalUpdateSettingsLoaded &&
        api.capabilities.value?.available &&
        binding
      "
      class="managed-update-settings-card"
      size="small"
      :bordered="false"
    >
      <template #title>托管项目统一更新设置</template>
      <template #extra>
        <a-tag color="blue">全局来源</a-tag>
      </template>
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :xs="24" :md="8">
            <a-form-item label="更新源">
              <a-select
                v-model:value="managedUpdateSettings.source"
                :disabled="globalUpdateSettingsLoading || operationRunning"
              >
                <a-select-option value="MirrorChyan">MirrorChyan</a-select-option>
                <a-select-option value="GitHub">GitHub</a-select-option>
                <a-select-option value="AutoSite">AutoSite（仅普通 AUTO-MAS）</a-select-option>
                <a-select-option value="CNB">CNB（仅普通 AUTO-MAS）</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="16">
            <a-form-item label="Mirror酱 CDK" extra="托管项目的 MirrorChyan 检查和安装统一继承此值">
              <a-input-password
                v-model:value="managedUpdateSettings.mirrorChyanCDK"
                :disabled="
                  globalUpdateSettingsLoading ||
                  operationRunning ||
                  managedUpdateSettings.source !== 'MirrorChyan'
                "
                placeholder="填写全局 MirrorChyan CDK"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-alert
          v-if="persistedGlobalUpdateSource === 'AutoSite' || persistedGlobalUpdateSource === 'CNB'"
          type="warning"
          show-icon
          message="托管远程操作已暂停"
          description="当前全局来源仅适用于普通 AUTO-MAS。请在顶部保存 MirrorChyan 或 GitHub 后，才能检查远程资源、下载并导入或升级托管资源。"
        />
        <a-space>
          <a-button
            type="primary"
            :loading="globalUpdateSettingsLoading || globalUpdateSettingsSaving"
            :disabled="operationRunning"
            @click="saveManagedUpdateSettings"
          >
            保存统一设置
          </a-button>
          <a-typography-text type="secondary">
            MirrorChyan/GitHub 用于托管远程资源；AutoSite/CNB 是普通 AUTO-MAS 来源。
          </a-typography-text>
        </a-space>
      </a-form>
    </a-card>

    <a-tabs
      v-if="
        !initialLoading &&
        globalUpdateSettingsLoaded &&
        api.capabilities.value?.available &&
        binding
      "
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
          :read-only="!safeMutationAvailable"
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

      <a-tab-pane v-if="safeMutationAvailable" key="operations" tab="导入与升级">
        <MaaFWProjectOperationsPanel
          :script-id="scriptId"
          :binding="binding"
          :features="effectiveFeatures"
          :busy="operationRunning"
          :remote-discovery="remoteDiscovery"
          :global-update-source="persistedGlobalUpdateSource"
          @convert="confirmConvert"
          @local-submit="confirmLocalSubmit"
          @remote-check="checkRemote"
          @remote-submit="confirmRemoteSubmit"
          @apply-plan="confirmApplyPlan"
          @cancel-plan="confirmCancelPlan"
        />
      </a-tab-pane>

      <a-tab-pane
        v-if="safeMutationAvailable && effectiveFeatures.garbageCollection !== false"
        key="maintenance"
        tab="空间回收"
      >
        <section class="maintenance-section">
          <div class="section-heading">
            <div>
              <h3>无引用资源回收</h3>
              <p>
                默认零宽限、零额外保留；仅固定资源、脚本引用和活动 lease
                受保护。“当前版本”指针本身不算引用。
              </p>
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
                <a-form-item label="本次宽限期（天）">
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
                <a-form-item label="本次额外保留最新数量">
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
import { useSettingsApi } from '@/composables/useSettingsApi'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import {
  getMaaFWManagedMutationUnavailableReason,
  hasMaaFWManagedSafeMutationContract,
  useMaaFWManagedApi,
  type MaaFWManagedBinding,
  type MaaFWManagedFeatures,
  type MaaFWManagedGarbageCollectionResult,
  type MaaFWManagedGlobalUpdateSource,
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
const DEFAULT_MANAGED_UPDATE_SOURCE: MaaFWManagedGlobalUpdateSource = 'MirrorChyan'

type GlobalUpdateSettingsValue = {
  source: MaaFWManagedGlobalUpdateSource
  mirrorChyanCDK: string
}

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
const { getSettings, updateSettings } = useSettingsApi()
const registryApi = useScriptRegistryApi()
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
const conversionSuccess = ref(false)
const conversionOriginalPath = ref('')
const gcForm = reactive({
  projectId: '',
  graceDays: 0,
  keepLatest: 0,
})
const managedUpdateSettings = reactive<{
  source: MaaFWManagedGlobalUpdateSource
  mirrorChyanCDK: string
}>({
  source: DEFAULT_MANAGED_UPDATE_SOURCE,
  mirrorChyanCDK: '',
})
const globalUpdateSettingsLoading = ref(false)
const globalUpdateSettingsLoaded = ref(false)
const globalUpdateSettingsSaving = ref(false)
const globalUpdateSettingsSnapshot = ref<GlobalUpdateSettingsValue | null>(null)
const persistedGlobalUpdateSource = computed<MaaFWManagedGlobalUpdateSource>(
  () => globalUpdateSettingsSnapshot.value?.source ?? DEFAULT_MANAGED_UPDATE_SOURCE
)
let versionsRequestSequence = 0
let managerLoadSequence = 0
let managerContextScriptId = ''
let loadedScriptId = ''
let globalUpdateSettingsRequestSequence = 0
let globalUpdateSettingsPending = 0
let managedUpdateSettingsSavePromise: Promise<void> | null = null
let overviewRefreshPromise: Promise<boolean> | null = null
let overviewRefreshContext: { scriptId: string; loadSequence: number } | null = null
let terminalReconciliationPromise: Promise<void> | null = null
let terminalRefreshPending = false
let terminalReconciliationGeneration = 0

const operationRunning = computed(
  () =>
    initialLoading.value ||
    overviewLoading.value ||
    versionsLoading.value ||
    mutationFinalizing.value ||
    globalUpdateSettingsLoading.value ||
    globalUpdateSettingsSaving.value ||
    api.loading.value ||
    api.progress.value.status === 'running'
)
const mutationRunning = computed(
  () => api.progress.value.status === 'running' || mutationFinalizing.value
)
const safeMutationAvailable = computed(() =>
  hasMaaFWManagedSafeMutationContract(api.capabilities.value)
)
const mutationUnavailableReason = computed(() =>
  getMaaFWManagedMutationUnavailableReason(api.capabilities.value)
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
  if (
    binding.value &&
    !binding.value.managed &&
    binding.value.scriptType !== 'MaaFW' &&
    binding.value.scriptType !== 'M9A'
  ) {
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
const progressStageLabel = computed(() => {
  const stage = String(api.progress.value.stage || '').trim()
  const labels: Record<string, string> = {
    completed: '操作已完成',
    failed: '操作失败',
    'project-import': '正在导入项目资源',
    'project-validate': '正在校验项目资源',
    'project-stage': '正在准备项目资源',
    'config-persisted': '正在保存项目配置',
    'runtime-resolve': '正在解析运行依赖',
    'runtime-install': '正在更新运行环境',
    'download:starting': '正在下载项目资源',
    'download:progress': '正在下载项目资源',
    'download:validated': '项目资源下载并校验完成',
    'resource-commit': '正在提交资源变更',
  }
  if (!stage) return '正在处理 MaaFW 资源'
  return labels[stage] || stage
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

const conversionSourcePathDescription = computed(() =>
  conversionOriginalPath.value
    ? '确认没有其他程序正在使用原目录后，可以自行删除；系统不会自动删除。'
    : '资源已复制到托管存储，原目录仍保留。请确认没有其他程序正在使用原目录后自行处理；系统不会自动删除。'
)

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

const loadOriginalProjectPath = async (loadSequence: number, scriptId: string) => {
  try {
    const records = await registryApi.getScripts(scriptId)
    if (!isCurrentManagerContext(loadSequence, scriptId)) return
    const info = asRecord(records[0]?.config?.Info)
    conversionOriginalPath.value = typeof info.Path === 'string' ? info.Path.trim() : ''
  } catch {
    // The manager remains usable when the registry read is unavailable; the
    // conversion alert will explain that the source path could not be read.
    if (isCurrentManagerContext(loadSequence, scriptId)) {
      conversionOriginalPath.value = ''
    }
  }
}

const copyConversionOriginalPath = async () => {
  const path = conversionOriginalPath.value
  if (!path) {
    message.warning('原目录路径暂不可用，请从脚本配置中查看')
    return
  }
  try {
    await navigator.clipboard.writeText(path)
    message.success('原目录路径已复制')
  } catch {
    message.error('复制原目录路径失败，请手动选择复制')
  }
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

const isCurrentManagerContext = (loadSequence: number, scriptId: string) =>
  !disposed && loadSequence === managerLoadSequence && props.scriptId === scriptId

const beginGlobalUpdateSettingsOperation = () => {
  globalUpdateSettingsPending += 1
  globalUpdateSettingsLoading.value = true
}

const endGlobalUpdateSettingsOperation = () => {
  globalUpdateSettingsPending = Math.max(0, globalUpdateSettingsPending - 1)
  globalUpdateSettingsLoading.value = globalUpdateSettingsPending > 0
}

type GlobalUpdateSettingsPatch = {
  Source?: MaaFWManagedGlobalUpdateSource
  MirrorChyanCDK?: string
}

type ManagedUpdateSettingsSnapshot = {
  source: MaaFWManagedGlobalUpdateSource
  mirrorChyanCDK: string
}

const normalizeGlobalUpdateSource = (value: unknown): MaaFWManagedGlobalUpdateSource => {
  if (value === 'GitHub' || value === 'MirrorChyan' || value === 'AutoSite' || value === 'CNB') {
    return value
  }
  return DEFAULT_MANAGED_UPDATE_SOURCE
}

const readGlobalUpdateSettings = (settings: {
  Update?: { Source?: unknown; MirrorChyanCDK?: unknown } | null
}): GlobalUpdateSettingsValue => {
  const update = settings.Update
  const source = normalizeGlobalUpdateSource(update?.Source)
  const mirrorChyanCDK = String(update?.MirrorChyanCDK ?? '').trim()
  return { source, mirrorChyanCDK }
}

const applyGlobalUpdateSettings = (settings: {
  Update?: { Source?: unknown; MirrorChyanCDK?: unknown } | null
}) => {
  const { source, mirrorChyanCDK } = readGlobalUpdateSettings(settings)
  managedUpdateSettings.source = source
  managedUpdateSettings.mirrorChyanCDK = mirrorChyanCDK
  globalUpdateSettingsSnapshot.value = { source, mirrorChyanCDK }
  globalUpdateSettingsLoaded.value = true
}

const loadManagedUpdateSettings = async (loadSequence: number, scriptId: string) => {
  const requestSequence = ++globalUpdateSettingsRequestSequence
  beginGlobalUpdateSettingsOperation()
  try {
    const settings = await getSettings()
    if (!settings) {
      if (
        requestSequence !== globalUpdateSettingsRequestSequence ||
        !isCurrentManagerContext(loadSequence, scriptId)
      ) {
        return
      }
      throw new Error('无法读取 AUTO-MAS 全局更新设置')
    }
    if (
      requestSequence !== globalUpdateSettingsRequestSequence ||
      !isCurrentManagerContext(loadSequence, scriptId)
    ) {
      return
    }
    applyGlobalUpdateSettings(settings)
  } finally {
    endGlobalUpdateSettingsOperation()
  }
}

const rollbackManagedUpdateSettings = async (
  scriptId: string,
  wasManaged: boolean,
  previous: ManagedUpdateSettingsSnapshot,
  globalPatch: GlobalUpdateSettingsPatch,
  globalWriteAttempted: boolean,
  settingsRequestSequence: number,
  loadSequence: number
) => {
  const rollbackErrors: string[] = []

  if (globalWriteAttempted && Object.keys(globalPatch).length) {
    const rollbackPatch: GlobalUpdateSettingsPatch = {}
    if (globalPatch.Source !== undefined) rollbackPatch.Source = previous.source
    if (globalPatch.MirrorChyanCDK !== undefined) {
      rollbackPatch.MirrorChyanCDK = previous.mirrorChyanCDK
    }
    try {
      const restored = await updateSettings({ Update: rollbackPatch })
      if (!restored) rollbackErrors.push('全局更新设置回滚失败')
    } catch (caught) {
      rollbackErrors.push(caught instanceof Error ? caught.message : '全局更新设置回滚失败')
    }
  }

  try {
    const settings = await getSettings()
    if (!settings) throw new Error('无法重新读取全局更新设置')
    if (!disposed && settingsRequestSequence === globalUpdateSettingsRequestSequence) {
      applyGlobalUpdateSettings(settings)
    }
  } catch (caught) {
    rollbackErrors.push(caught instanceof Error ? caught.message : '保存失败后的全局设置刷新失败')
  }

  if (wasManaged) {
    try {
      const refreshedBinding = await api.getCurrentBinding(scriptId)
      if (isCurrentManagerContext(loadSequence, scriptId)) binding.value = refreshedBinding
    } catch (caught) {
      rollbackErrors.push(caught instanceof Error ? caught.message : '保存失败后的项目绑定刷新失败')
    }
  }

  return rollbackErrors
}

const saveManagedUpdateSettings = async () => {
  if (
    disposed ||
    globalUpdateSettingsSaving.value ||
    globalUpdateSettingsLoading.value ||
    operationRunning.value
  ) {
    return
  }
  const previousGlobal = globalUpdateSettingsSnapshot.value
  if (!globalUpdateSettingsLoaded.value || !previousGlobal) {
    message.warning('全局更新设置尚未读取完成，请刷新后重试')
    return
  }

  const scriptId = props.scriptId
  const saveLoadSequence = managerLoadSequence
  const wasManaged = binding.value?.managed === true
  const previous: ManagedUpdateSettingsSnapshot = previousGlobal
  const currentMirrorChyanCDK = managedUpdateSettings.mirrorChyanCDK.trim()
  managedUpdateSettings.mirrorChyanCDK = currentMirrorChyanCDK
  const globalPatch: GlobalUpdateSettingsPatch = {}
  if (managedUpdateSettings.source !== previous.source) {
    globalPatch.Source = managedUpdateSettings.source
  }
  if (currentMirrorChyanCDK !== previous.mirrorChyanCDK) {
    globalPatch.MirrorChyanCDK = currentMirrorChyanCDK
  }

  const hasGlobalChanges = Object.keys(globalPatch).length > 0
  if (!hasGlobalChanges) {
    message.info('更新设置没有变化')
    return
  }

  const settingsRequestSequence = ++globalUpdateSettingsRequestSequence
  globalUpdateSettingsSaving.value = true
  beginGlobalUpdateSettingsOperation()
  let resolveSaveCompletion!: () => void
  const saveCompletion = new Promise<void>(resolve => {
    resolveSaveCompletion = resolve
  })
  managedUpdateSettingsSavePromise = saveCompletion
  let globalWriteAttempted = false
  try {
    if (hasGlobalChanges) {
      globalWriteAttempted = true
      const saved = await updateSettings({ Update: globalPatch })
      if (!saved) throw new Error('全局更新来源或 MirrorChyan CDK 保存失败')
    }

    const settings = await getSettings()
    if (!settings) throw new Error('设置已保存，但重新读取全局更新设置失败')
    const refreshedGlobal = readGlobalUpdateSettings(settings)
    if (globalPatch.Source !== undefined && refreshedGlobal.source !== globalPatch.Source) {
      throw new Error('全局更新来源刷新后与请求不一致')
    }
    if (
      globalPatch.MirrorChyanCDK !== undefined &&
      refreshedGlobal.mirrorChyanCDK !== currentMirrorChyanCDK
    ) {
      throw new Error('MirrorChyan CDK 刷新后与请求不一致')
    }
    if (!disposed && settingsRequestSequence === globalUpdateSettingsRequestSequence) {
      applyGlobalUpdateSettings(settings)
    }
    if (wasManaged) {
      const refreshedBinding = await api.getCurrentBinding(scriptId)
      if (isCurrentManagerContext(saveLoadSequence, scriptId)) binding.value = refreshedBinding
    }

    if (
      isCurrentManagerContext(saveLoadSequence, scriptId) &&
      settingsRequestSequence === globalUpdateSettingsRequestSequence
    ) {
      pageError.value = ''
      message.success('全局更新设置已保存并刷新')
    }
  } catch (caught) {
    let rollbackErrors: string[] = []
    try {
      rollbackErrors = await rollbackManagedUpdateSettings(
        scriptId,
        wasManaged,
        previous,
        globalPatch,
        globalWriteAttempted,
        settingsRequestSequence,
        saveLoadSequence
      )
    } catch (rollbackCaught) {
      rollbackErrors.push(
        rollbackCaught instanceof Error ? rollbackCaught.message : '保存失败后的回滚异常'
      )
      try {
        const settings = await getSettings()
        if (!settings) throw new Error('无法重新读取全局更新设置')
        if (!disposed && settingsRequestSequence === globalUpdateSettingsRequestSequence) {
          applyGlobalUpdateSettings(settings)
        }
      } catch (refreshCaught) {
        rollbackErrors.push(
          refreshCaught instanceof Error ? refreshCaught.message : '保存失败后的全局设置刷新失败'
        )
      }
      if (wasManaged) {
        try {
          const refreshedBinding = await api.getCurrentBinding(scriptId)
          if (isCurrentManagerContext(saveLoadSequence, scriptId)) {
            binding.value = refreshedBinding
          }
        } catch (bindingRefreshCaught) {
          rollbackErrors.push(
            bindingRefreshCaught instanceof Error
              ? bindingRefreshCaught.message
              : '保存失败后的项目绑定刷新失败'
          )
        }
      }
    }
    const reason = caught instanceof Error ? caught.message : '保存托管项目更新设置失败'
    const rollbackMessage = rollbackErrors.length
      ? `；回滚或刷新未完全成功：${rollbackErrors.join('；')}`
      : '；已回滚并刷新为保存前状态'
    if (isCurrentManagerContext(saveLoadSequence, scriptId)) {
      reportFailure(new Error(`${reason}${rollbackMessage}`), '保存托管项目更新设置失败')
    }
  } finally {
    endGlobalUpdateSettingsOperation()
    globalUpdateSettingsSaving.value = false
    if (managedUpdateSettingsSavePromise === saveCompletion) {
      managedUpdateSettingsSavePromise = null
    }
    resolveSaveCompletion()
  }
}

const loadManager = async () => {
  const loadSequence = ++managerLoadSequence
  const scriptId = props.scriptId
  const contextChanged = Boolean(managerContextScriptId && managerContextScriptId !== scriptId)
  managerContextScriptId = scriptId
  if (contextChanged) {
    conversionSuccess.value = false
    conversionOriginalPath.value = ''
  }
  const previousManaged = binding.value?.managed
  const previousLoadedScriptId = loadedScriptId
  const wasFinalizing = mutationFinalizing.value
  initialLoading.value = true
  pageError.value = ''
  remoteDiscovery.value = null
  gcPreview.value = null
  gcPreviewInput.value = null
  globalUpdateSettingsLoaded.value = false
  globalUpdateSettingsSnapshot.value = null
  binding.value = null
  projects.value = []
  versions.value = []
  runtimes.value = []
  selectedProjectId.value = ''
  overviewLoading.value = false
  versionsLoading.value = false
  loadedScriptId = ''
  api.resetProgress(contextChanged)
  try {
    const pendingSave = managedUpdateSettingsSavePromise
    if (pendingSave) await pendingSave.catch(() => undefined)
    if (!isCurrentManagerContext(loadSequence, scriptId)) return

    // Settings and capability discovery are independent network reads.  Do
    // them together so a slow global-config request cannot make the manager
    // appear frozen before the project overview starts loading.
    const [, capabilities] = await Promise.all([
      loadManagedUpdateSettings(loadSequence, scriptId),
      api.getCapabilities(),
      loadOriginalProjectPath(loadSequence, scriptId),
    ])
    if (!isCurrentManagerContext(loadSequence, scriptId) || !capabilities.available) return
    const progressPromise = hasMaaFWManagedSafeMutationContract(capabilities)
      ? api.resumeProgress(scriptId)
      : Promise.resolve(null)
    const overviewPromise = api.getOverview(scriptId)
    const [, overview] = await Promise.all([progressPromise, overviewPromise])
    if (!isCurrentManagerContext(loadSequence, scriptId)) return
    binding.value = overview.binding
    projects.value = overview.projects
    runtimes.value = overview.runtimes
    loadedScriptId = scriptId
    activeTab.value =
      overview.binding.managed || !hasMaaFWManagedSafeMutationContract(capabilities)
        ? 'resources'
        : 'operations'
    if (
      previousLoadedScriptId === scriptId &&
      previousManaged === false &&
      overview.binding.managed
    ) {
      emit('converted', scriptId)
    }
    const preferredProject = overview.binding.projectId || overview.projects[0]?.projectId || ''
    if (preferredProject) {
      const versionsLoaded = await selectProject(preferredProject, false, scriptId, loadSequence)
      if (!versionsLoaded) return
    } else {
      selectedProjectId.value = ''
      versions.value = []
    }
    if (wasFinalizing && !terminalRefreshPending) emit('refreshed')
    if (!terminalRefreshPending) mutationFinalizing.value = false
  } catch (caught) {
    if (!isCurrentManagerContext(loadSequence, scriptId)) return
    reportFailure(caught, '读取 MaaFW 项目管理数据失败')
  } finally {
    if (isCurrentManagerContext(loadSequence, scriptId)) {
      initialLoading.value = false
      if (terminalRefreshPending) {
        terminalRefreshPending = false
        queueTerminalReconciliation()
      }
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
  const refreshScriptId = props.scriptId
  const refreshLoadSequence = managerLoadSequence
  if (
    overviewRefreshPromise &&
    overviewRefreshContext?.scriptId === refreshScriptId &&
    overviewRefreshContext.loadSequence === refreshLoadSequence
  ) {
    return overviewRefreshPromise
  }
  if (!isCurrentManagerContext(refreshLoadSequence, refreshScriptId)) {
    return Promise.resolve(false)
  }
  const refreshGeneration = terminalReconciliationGeneration
  const pendingSave = managedUpdateSettingsSavePromise
  let refreshPromise!: Promise<boolean>
  refreshPromise = (async () => {
    overviewLoading.value = true
    pageError.value = ''
    globalUpdateSettingsLoaded.value = false
    globalUpdateSettingsSnapshot.value = null
    try {
      if (pendingSave) await pendingSave.catch(() => undefined)
      if (!isCurrentManagerContext(refreshLoadSequence, refreshScriptId)) return false
      const settingsPromise = loadManagedUpdateSettings(refreshLoadSequence, refreshScriptId).catch(
        caught => caught
      )
      const overview = await api.getOverview(refreshScriptId)
      const settingsError = await settingsPromise
      if (!isCurrentManagerContext(refreshLoadSequence, refreshScriptId)) return false
      const convertedToManaged = binding.value?.managed === false && overview.binding.managed
      binding.value = overview.binding
      projects.value = overview.projects
      runtimes.value = overview.runtimes
      loadedScriptId = refreshScriptId
      if (settingsError) {
        reportFailure(settingsError, '读取 AUTO-MAS 全局更新设置失败')
      }
      if (convertedToManaged) {
        activeTab.value = 'resources'
        emit('converted', refreshScriptId)
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
        const versionsLoaded = await selectProject(
          projectId,
          true,
          refreshScriptId,
          refreshLoadSequence
        )
        if (!isCurrentManagerContext(refreshLoadSequence, refreshScriptId) || !versionsLoaded) {
          return false
        }
      } else {
        selectedProjectId.value = ''
        versions.value = []
      }
      emit('refreshed')
      finalizeTerminalReconciliation(refreshGeneration)
      return true
    } catch (caught) {
      if (isCurrentManagerContext(refreshLoadSequence, refreshScriptId)) {
        reportFailure(caught, '刷新 MaaFW 项目管理数据失败')
      }
      return false
    } finally {
      if (isCurrentManagerContext(refreshLoadSequence, refreshScriptId)) {
        overviewLoading.value = false
      }
    }
  })().finally(() => {
    if (overviewRefreshPromise === refreshPromise) {
      overviewRefreshPromise = null
      overviewRefreshContext = null
    }
  })
  overviewRefreshPromise = refreshPromise
  overviewRefreshContext = { scriptId: refreshScriptId, loadSequence: refreshLoadSequence }
  return refreshPromise
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

const selectProject = async (
  projectId: string,
  force = false,
  scriptId = props.scriptId,
  loadSequence = managerLoadSequence
): Promise<boolean> => {
  if (!isCurrentManagerContext(loadSequence, scriptId)) return false
  if (!projectId || (!force && projectId === selectedProjectId.value && versions.value.length)) {
    return true
  }
  const requestSequence = ++versionsRequestSequence
  selectedProjectId.value = projectId
  versionsLoading.value = true
  try {
    const nextVersions = await api.listVersions(scriptId, projectId)
    if (
      !isCurrentManagerContext(loadSequence, scriptId) ||
      requestSequence !== versionsRequestSequence ||
      selectedProjectId.value !== projectId
    ) {
      return false
    }
    versions.value = nextVersions
    return true
  } catch (caught) {
    if (
      !isCurrentManagerContext(loadSequence, scriptId) ||
      requestSequence !== versionsRequestSequence ||
      selectedProjectId.value !== projectId
    ) {
      return false
    }
    versions.value = []
    reportFailure(caught, `读取项目 ${projectId} 的版本失败`)
    return false
  } finally {
    if (
      requestSequence === versionsRequestSequence &&
      isCurrentManagerContext(loadSequence, scriptId)
    ) {
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
  const sourcePath = conversionOriginalPath.value
  const wasOrdinaryProject = binding.value?.managed === false
  showManagedConfirm({
    title: '转换为托管 MaaFW 项目？',
    content:
      '后端会从当前项目路径导入受版本保护的资源，并保留此脚本 ID、全部用户和任务关联。转换失败时不会报告为已完成。',
    okText: '确认转换',
    cancelText: '取消',
    onOk() {
      void runAndRefresh(
        () => api.convert({ scriptId: props.scriptId, ...input }),
        '已转换为托管 MaaFW 项目'
      ).then(result => {
        if (
          (result && (result.converted || result.idempotent)) ||
          (!result && wasOrdinaryProject && binding.value?.managed === true)
        ) {
          conversionSuccess.value = true
          conversionOriginalPath.value = sourcePath
          activeTab.value = 'resources'
        }
      })
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
    content: '取消固定后，如果没有脚本引用或活动 lease，该版本会在下一次 GC 被回收。',
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
    content: '取消固定后，如果没有脚本引用或活动 lease，该运行时会在下一次 GC 被回收。',
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
.maafw-project-manager-workspace {
  padding: 4px 4px 8px;
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.manager-version {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.manager-readonly-alert {
  margin-bottom: 16px;
}

.managed-update-settings-card {
  margin-bottom: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
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

.conversion-success-alert {
  margin-bottom: 16px;
}

.conversion-success-description {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.conversion-source-path {
  align-items: center;
  max-width: 100%;
}

.conversion-source-path :deep(.ant-typography) {
  max-width: min(720px, 100%);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversion-source-path-missing {
  color: var(--ant-color-text-secondary);
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

.gc-detail {
  margin: 0;
  padding: 12px;
  max-height: 240px;
  overflow: auto;
  color: var(--ant-color-text);
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  border-radius: 6px;
  font-family: var(--ant-font-family-code, Consolas, monospace);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.operation-logs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 12px;
  max-height: 260px;
  overflow: auto;
  list-style: none;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  border-radius: 8px;
}

.operation-logs li {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  color: var(--ant-color-text);
  line-height: 1.55;
  word-break: break-word;
}

.operation-log-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  border-radius: 50%;
  font-size: 12px;
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
