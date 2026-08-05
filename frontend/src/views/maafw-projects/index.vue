<template>
  <div class="maafw-projects-page">
    <header class="page-header">
      <div>
        <h1>MaaFW 项目与资源</h1>
        <p>统一查看 MaaFW 项目版本、资源引用和共享运行时，并管理普通与托管项目。</p>
      </div>
      <a-space>
        <a-button @click="goToSource">
          <template #icon><ArrowLeftOutlined /></template>
          {{ entrySource === 'edit' ? '返回脚本配置' : '返回脚本管理' }}
        </a-button>
        <a-button
          v-if="selectedScript && entrySource !== 'edit'"
          type="primary"
          @click="editSelectedScript"
        >
          <template #icon><EditOutlined /></template>
          编辑当前脚本
        </a-button>
      </a-space>
    </header>

    <MaaFWGlobalInventoryPanel
      :inventory="inventory"
      :loading="inventoryLoading"
      :error="inventoryError"
      :gc-available="globalGcAvailable"
      :gc-unavailable-reason="globalGcUnavailableReason"
      :gc-loading="managedApi.loading.value"
      :gc-error="globalGcError"
      :gc-preview="globalGcPreview"
      :gc-preview-input="globalGcPreviewInput"
      :gc-progress="managedApi.progress.value"
      @refresh="loadInventory"
      @gc-preview="previewGlobalGarbageCollection"
      @gc-apply="applyGlobalGarbageCollection"
      @gc-reset="resetGlobalGarbageCollectionPreview"
    />

    <a-alert
      v-if="scriptListError"
      type="error"
      show-icon
      message="MaaFW 脚本列表加载失败"
      :description="scriptListError"
    >
      <template #action>
        <a-button size="small" :loading="scriptListLoading" @click="loadScripts">重试</a-button>
      </template>
    </a-alert>

    <div v-else-if="scriptListLoading" class="page-loading">
      <a-spin size="large" tip="正在读取 MaaFW 项目" />
    </div>

    <a-card v-else-if="maafwScripts.length === 0" class="empty-context-card" :bordered="false">
      <a-empty description="当前没有 MaaFW 脚本，仍可在上方查看未绑定的托管资源">
        <a-button type="primary" @click="goToScripts">前往脚本管理创建项目</a-button>
      </a-empty>
    </a-card>

    <template v-else>
      <a-alert
        v-if="selectionError"
        type="warning"
        show-icon
        message="无法打开指定的 MaaFW 项目"
        :description="selectionError"
      />

      <a-card class="context-manager-card" :bordered="false">
        <div class="context-layout">
          <div class="context-selector">
            <label for="maafw-project-context">管理上下文</label>
            <a-select
              id="maafw-project-context"
              :value="selectedScriptId"
              size="large"
              :disabled="workspaceBusy"
              @change="handleScriptChange"
            >
              <a-select-option v-for="script in maafwScripts" :key="script.id" :value="script.id">
                {{ getScriptLabel(script) }} · {{ shortId(script.id) }}
              </a-select-option>
            </a-select>
            <span>资源操作会以所选脚本的绑定和引用关系为准。</span>
          </div>

          <div v-if="selectedScript" class="context-summary">
            <div>
              <strong>{{ getScriptLabel(selectedScript) }}</strong>
              <span>{{ selectedScript.user_count }} 个用户</span>
            </div>
            <a-typography-text type="secondary">
              {{ getScriptContextLabel(selectedScript) }}
            </a-typography-text>
          </div>
        </div>
        <a-typography-text v-if="selectedProjectPath" class="project-path" type="secondary">
          项目路径：{{ selectedProjectPath }}
        </a-typography-text>
        <div class="context-manager-divider" />
        <MaaFWProjectManagerWorkspace
          v-if="selectedScriptId"
          :key="selectedScriptId"
          :script-id="selectedScriptId"
          @converted="handleWorkspaceChanged"
          @refreshed="handleWorkspaceChanged"
          @busy-change="workspaceBusy = $event"
          @operation-change="operationRunning = $event"
        />
      </a-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { Modal } from 'ant-design-vue'
import { ArrowLeftOutlined, EditOutlined } from '@ant-design/icons-vue'
import {
  getMaaFWManagedMutationUnavailableReason,
  hasMaaFWManagedSafeMutationContract,
  useMaaFWManagedApi,
  type MaaFWManagedGarbageCollectionInput,
  type MaaFWManagedGarbageCollectionResult,
  type MaaFWManagedGlobalInventory,
} from '@/composables/useMaaFWManagedApi'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import type { ScriptRecord } from '@/types/scriptRegistry'
import { getMaaFWProjectLabel } from '@/utils/maafwProjectLabel'
import MaaFWGlobalInventoryPanel from './components/MaaFWGlobalInventoryPanel.vue'
import MaaFWProjectManagerWorkspace from './components/MaaFWProjectManagerWorkspace.vue'

defineOptions({ name: 'MaaFWProjectsPage' })

const logger = window.electronAPI.getLogger('MaaFW项目管理')
const route = useRoute()
const router = useRouter()
const registryApi = useScriptRegistryApi()
const managedApi = useMaaFWManagedApi()
const MANAGER_CONFIRM_Z_INDEX = 950

const maafwScripts = ref<ScriptRecord[]>([])
const inventory = ref<MaaFWManagedGlobalInventory | null>(null)
const inventoryLoading = ref(false)
const inventoryError = ref('')
const globalGcError = ref('')
const globalGcPreview = ref<MaaFWManagedGarbageCollectionResult | null>(null)
const globalGcPreviewInput = ref<MaaFWManagedGarbageCollectionInput | null>(null)
const selectedScriptId = ref('')
const scriptListLoading = ref(false)
const scriptListError = ref('')
const selectionError = ref('')
const workspaceBusy = ref(false)
const operationRunning = ref(false)
let contextRefreshPromise: Promise<void> | null = null
let pendingInternalScriptId = ''

const globalGcAvailable = computed(
  () =>
    hasMaaFWManagedSafeMutationContract(managedApi.capabilities.value) &&
    managedApi.capabilities.value?.features.garbageCollection === true
)
const globalGcUnavailableReason = computed(() =>
  globalGcAvailable.value
    ? ''
    : getMaaFWManagedMutationUnavailableReason(managedApi.capabilities.value)
)

const selectedScript = computed(
  () => maafwScripts.value.find(script => script.id === selectedScriptId.value) || null
)

const selectedProjectPath = computed(() => {
  const info = asRecord(selectedScript.value?.config?.Info)
  return typeof info.Path === 'string' ? info.Path : ''
})

const requestedScriptId = computed(() => {
  const value = route.query.scriptId
  return Array.isArray(value) ? value[0] || '' : value || ''
})

const entrySource = computed<'edit' | 'scripts'>(() =>
  route.query.from === 'edit' ? 'edit' : 'scripts'
)

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}

const getScriptLabel = (script: ScriptRecord) => {
  return getMaaFWProjectLabel(script)
}

const getScriptContextLabel = (script: ScriptRecord) => {
  if (script.type === 'MaaFWManaged') return '托管项目'
  if (script.type === 'MaaFW') return '普通项目'
  return 'MFW 项目'
}

const shortId = (scriptId: string) =>
  scriptId.length > 12 ? `${scriptId.slice(0, 8)}…${scriptId.slice(-4)}` : scriptId

const managerQuery = (scriptId: string) => ({ scriptId, from: entrySource.value })

const replaceManagerScript = (scriptId: string) => {
  pendingInternalScriptId = scriptId
  void router.replace({ name: 'MaaFWProjects', query: managerQuery(scriptId) }).finally(() => {
    if (pendingInternalScriptId === scriptId) pendingInternalScriptId = ''
  })
}

const syncSelectedScript = () => {
  const requested = requestedScriptId.value
  if (requested) {
    const requestedScript = maafwScripts.value.find(script => script.id === requested)
    if (!requestedScript) {
      workspaceBusy.value = false
      operationRunning.value = false
      selectedScriptId.value = ''
      selectionError.value = `指定脚本 ${shortId(requested)} 不存在，或不是可管理的 MaaFW 项目。请重新选择。`
      return
    }
    selectedScriptId.value = requestedScript.id
    selectionError.value = ''
    return
  }
  const nextScript =
    maafwScripts.value.find(script => script.id === selectedScriptId.value) || maafwScripts.value[0]
  selectedScriptId.value = nextScript?.id || ''
  selectionError.value = ''
  if (nextScript) {
    replaceManagerScript(nextScript.id)
  }
}

const refreshScriptRecords = async () => {
  const [records, descriptors] = await Promise.all([
    registryApi.getScripts(),
    registryApi.getScriptTypes(),
  ])
  const maafwTypes = new Set(
    descriptors
      .filter(descriptor => asRecord(descriptor.client).framework === 'maafw')
      .map(descriptor => descriptor.type_key)
  )
  maafwTypes.add('MaaFW')
  maafwTypes.add('MaaFWManaged')
  maafwTypes.add('M9A')
  maafwScripts.value = records.filter(script => maafwTypes.has(script.type))
  syncSelectedScript()
}

const loadScripts = async () => {
  scriptListLoading.value = true
  scriptListError.value = ''
  try {
    await refreshScriptRecords()
  } catch (caught) {
    const reason = caught instanceof Error ? caught.message : '读取 MaaFW 脚本列表失败'
    scriptListError.value = reason
    logger.error(`读取 MaaFW 脚本列表失败: ${reason}`)
  } finally {
    scriptListLoading.value = false
  }
}

const loadInventory = async () => {
  inventoryLoading.value = true
  inventoryError.value = ''
  globalGcError.value = ''
  globalGcPreview.value = null
  globalGcPreviewInput.value = null
  try {
    const capabilities = await managedApi.getCapabilities()
    if (hasMaaFWManagedSafeMutationContract(capabilities)) {
      try {
        await managedApi.resumeProgress('')
      } catch (caught) {
        logger.warn(
          `恢复全局 MaaFW 回收进度失败：${caught instanceof Error ? caught.message : String(caught)}`
        )
      }
    }
    inventory.value = await managedApi.getInventory()
  } catch (caught) {
    const reason = caught instanceof Error ? caught.message : '读取 MaaFW 全局资源盘点失败'
    inventoryError.value = reason
    logger.error(`读取 MaaFW 全局资源盘点失败: ${reason}`)
  } finally {
    inventoryLoading.value = false
  }
}

const previewGlobalGarbageCollection = async (input: MaaFWManagedGarbageCollectionInput) => {
  if (!globalGcAvailable.value) return
  globalGcError.value = ''
  globalGcPreview.value = null
  globalGcPreviewInput.value = null
  try {
    const preview = await managedApi.collectGarbage(undefined, input)
    if (preview) {
      globalGcPreview.value = preview
      globalGcPreviewInput.value = input
      return
    }
    globalGcError.value =
      managedApi.progress.value.status === 'unknown'
        ? '全局回收预览请求中断，结果待核对；请刷新盘点后重试。'
        : '全局回收预览完成但未返回结果，请刷新盘点后重试。'
  } catch (caught) {
    const reason = caught instanceof Error ? caught.message : '全局回收预览失败'
    globalGcError.value = reason
    logger.error(`全局回收预览失败：${reason}`)
  }
}

const resetGlobalGarbageCollectionPreview = () => {
  globalGcPreview.value = null
  globalGcPreviewInput.value = null
  globalGcError.value = ''
}

const applyGlobalGarbageCollection = async (input: MaaFWManagedGarbageCollectionInput) => {
  if (!globalGcAvailable.value) return
  globalGcError.value = ''
  try {
    const result = await managedApi.collectGarbage(undefined, { ...input, dryRun: false })
    if (!result && managedApi.progress.value.status !== 'success') {
      globalGcError.value =
        managedApi.progress.value.status === 'unknown'
          ? '全局回收结果待核对；请刷新盘点后确认资源状态。'
          : '全局回收未返回结果，请刷新盘点后重试。'
      return
    }
    globalGcPreview.value = null
    globalGcPreviewInput.value = null
    await loadInventory()
  } catch (caught) {
    const reason = caught instanceof Error ? caught.message : '执行全局回收失败'
    globalGcError.value = reason
    logger.error(`执行全局回收失败：${reason}`)
  }
}

const handleScriptChange = (value: unknown) => {
  const scriptId = typeof value === 'string' ? value : ''
  if (!scriptId || workspaceBusy.value) return
  selectedScriptId.value = scriptId
  selectionError.value = ''
  replaceManagerScript(scriptId)
}

const handleWorkspaceChanged = () => {
  if (contextRefreshPromise) return contextRefreshPromise
  contextRefreshPromise = Promise.all([refreshScriptRecords(), loadInventory()])
    .then(() => undefined)
    .catch(caught => {
      const reason = caught instanceof Error ? caught.message : '刷新 MaaFW 脚本状态失败'
      logger.warn(`刷新 MaaFW 脚本状态失败: ${reason}`)
    })
    .finally(() => {
      contextRefreshPromise = null
    })
  return contextRefreshPromise
}

const goToScripts = () => {
  void router.push({ name: 'Scripts' })
}

const goToSource = () => {
  if (entrySource.value === 'edit' && selectedScriptId.value) {
    editSelectedScript()
    return
  }
  goToScripts()
}

const editSelectedScript = () => {
  if (!selectedScriptId.value) return
  void router.push({ name: 'MaaFWScriptEdit', params: { id: selectedScriptId.value } })
}

watch(requestedScriptId, () => {
  if (!scriptListLoading.value && maafwScripts.value.length > 0) syncSelectedScript()
})

const confirmOperationNavigation = () => {
  if (!operationRunning.value) return true
  return new Promise<boolean>(resolve => {
    Modal.confirm({
      zIndex: MANAGER_CONFIRM_Z_INDEX,
      title: '资源操作仍在进行',
      content: '离开页面不会取消后端操作。稍后返回时请刷新项目与资源状态。',
      okText: '仍然离开',
      cancelText: '继续查看',
      onOk: () => {
        workspaceBusy.value = false
        operationRunning.value = false
        resolve(true)
      },
      onCancel: () => resolve(false),
    })
  })
}

onBeforeRouteUpdate((to, from) => {
  const toScriptId = Array.isArray(to.query.scriptId)
    ? to.query.scriptId[0] || ''
    : to.query.scriptId || ''
  const fromScriptId = Array.isArray(from.query.scriptId)
    ? from.query.scriptId[0] || ''
    : from.query.scriptId || ''
  if (toScriptId === fromScriptId || toScriptId === pendingInternalScriptId) return true
  return confirmOperationNavigation()
})

onBeforeRouteLeave(confirmOperationNavigation)

onMounted(() => {
  void Promise.all([loadScripts(), loadInventory()])
})
</script>

<style scoped>
.maafw-projects-page {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  gap: 24px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.page-header h1 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 28px;
  line-height: 1.3;
}

.page-header p {
  margin: 8px 0 0;
  color: var(--ant-color-text-secondary);
}

.page-loading {
  display: flex;
  min-height: 360px;
  align-items: center;
  justify-content: center;
}

.context-manager-card,
.context-card {
  background: var(--ant-color-bg-container);
}

.context-manager-divider {
  height: 1px;
  margin: 24px 0 8px;
  background: var(--ant-color-border-secondary);
}

.empty-context-card {
  background: var(--ant-color-bg-container);
}

.context-layout {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) minmax(240px, auto);
  gap: 24px;
  align-items: end;
}

.context-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.context-selector label {
  color: var(--ant-color-text);
  font-weight: 500;
}

.context-selector > span,
.context-summary span {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.context-summary {
  display: flex;
  min-width: 240px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.context-summary > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.context-summary strong {
  overflow: hidden;
  color: var(--ant-color-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-path {
  display: block;
  margin-top: 16px;
  overflow-wrap: anywhere;
}

@media (max-width: 960px) {
  .context-layout {
    grid-template-columns: 1fr;
  }

  .page-header {
    flex-direction: column;
  }

  .context-summary {
    min-width: 0;
  }
}
</style>
