<template>
  <div class="plugin-page">
    <PageHeader
      class="plugin-page-header"
      title="插件管理"
      subtitle="管理插件实例、运行状态与声明式配置"
      compact
      transparent
    >
      <div class="plugin-summary" aria-label="插件实例概览">
        <span>{{ instances.length }} 个实例</span>
        <span aria-hidden="true">·</span>
        <span>{{ activeInstanceCount }} 个运行中</span>
      </div>
    </PageHeader>

    <Toolbar class="plugin-toolbar" position="both" aria-label="插件管理工具栏">
      <span class="toolbar-hint">选择实例后可编辑配置；拖拽把手可排序或移动分组</span>
      <template #trailing>
        <a-input
          v-model:value="keyword"
          placeholder="搜索插件"
          allow-clear
          size="small"
          class="toolbar-search"
        >
          <template #prefix>
            <SearchOutlined />
          </template>
        </a-input>
        <a-button :loading="loading" @click="handleRefresh">刷新</a-button>
        <a-button :loading="reloadingAll" @click="handleReloadAll">重载全部</a-button>
        <a-button @click="openAddModal">
          <PlusOutlined />
          新增实例
        </a-button>
        <a-button type="primary" @click="openPluginMarket">
          <DownloadOutlined />
          获取插件
        </a-button>
      </template>
    </Toolbar>

    <main class="plugin-workspace">
      <aside class="plugin-list-pane">
        <PluginInstanceList
          :instances="instances"
          :ordered-instances="orderedInstances"
          :filtered-instances="filteredInstances"
          :runtime-states="runtimeStates"
          :layout="pluginLayout.layout.value"
          :selected-instance-id="selectedInstanceId"
          :toggling-instance-id="togglingInstanceId"
          :keyword="keyword"
          :version="version"
          :plugin-packages="pluginPackages"
          :plugin-services="pluginServices"
          :plugin-routes="pluginRoutes"
          :schema-errors="schemaErrors"
          @update:keyword="keyword = $event"
          @select="selectInstance"
          @toggle-enabled="handleToggleEnabled"
          @drag-end="onDragEnd"
          @create-group="createGroup"
          @group-action="handleGroupAction"
          @open-add-modal="openAddModal"
          @open-plugin-market="openPluginMarket"
          @open-plugin-dir="handleOpenPluginDir"
          @check-update="handleCheckUpdate"
          @uninstall-plugin="handleUninstallInstance"
        />
      </aside>

      <section class="plugin-detail-pane">
        <PluginInstanceDetail
          ref="pluginInstanceDetailRef"
          :selected-instance="selectedInstance"
          :edit-form="editForm"
          :is-dirty="isDirty"
          :edit-snapshot="editSnapshot"
          :submitting="submitting"
          :action-loading-id="pluginActionLoadingId"
          :uninstalling-plugin="uninstallingPlugin"
          :active-schema="activeSchema"
          :active-schema-entries="activeSchemaEntries"
          :current-schema-error="currentSchemaError"
          :hidden-schema-fields="hiddenSchemaFields"
          :runtime-state="selectedRuntimeState"
          :selected-plugin-service="selectedPluginService"
          :plugin-actions="selectedPluginActions"
          :selected-plugin-package-name="selectedPluginPackageName"
          :can-uninstall="canUninstallSelectedPlugin"
          @submit-edit="submitEdit"
          @reset-edit="resetEdit"
          @open-json-preview="openJsonPreview"
          @reload-instance="handleReloadInstance"
          @reload-plugin="handleReloadPlugin"
          @uninstall-plugin="handleUninstallPlugin"
          @delete-instance="handleDeleteInstance"
          @trigger-action="handleTriggerAction"
          @trigger-schema-action="handleTriggerSchemaAction"
          @validation-change="handleSchemaValidationChange"
          @sensitive-dirty-change="sensitiveDirty = $event"
          @update:edit-form="Object.assign(editForm, $event)"
          @copy-diagnostics="copyDiagnostics"
        />
      </section>
    </main>

    <PluginAddModal
      :visible="addModalVisible"
      :submitting="submitting"
      :add-form="addForm"
      :keyword="addPluginKeyword"
      :discovered-plugins="discoveredPluginOptions"
      :filtered-options="filteredDiscoveredPluginOptions"
      :selected-add-plugin-option="selectedAddPluginOption"
      :selected-add-plugin-service-rows="selectedAddPluginServiceRows"
      @close="addModalVisible = false"
      @submit-add="submitAdd"
      @update:add-plugin="addForm.plugin = $event"
      @update:add-name="addForm.name = $event"
      @update:add-enabled="addForm.enabled = $event"
      @update:keyword="addPluginKeyword = $event"
    />

    <a-modal v-model:open="jsonPreviewVisible" title="当前配置 JSON" width="760px" :footer="null">
      <a-textarea :value="jsonPreviewText" :rows="18" readonly />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Input, message, Modal } from 'ant-design-vue'
import { DownloadOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/mac/PageHeader.vue'
import Toolbar from '@/components/mac/Toolbar.vue'
import { sanitizeErrorForLog } from '@/composables/useSensitiveFieldStrategy'
import { usePluginData } from './plugin/composables/usePluginData'
import { usePluginLayout } from './plugin/composables/usePluginLayout'
import {
  isBooleanSchema,
  hasEnableSchema as checkHasEnableSchema,
  parseConfigText,
  setConfigObjectToText,
  collectSchemaFieldErrors,
  getSchemaButtonAction,
  getFieldLabel,
} from './plugin/composables/usePluginSchema'
import PluginInstanceList from './plugin/components/PluginInstanceList.vue'
import PluginInstanceDetail from './plugin/components/PluginInstanceDetail.vue'
import PluginAddModal from './plugin/components/PluginAddModal.vue'
import type {
  PluginInstance,
  PluginSchemaField,
  PluginServiceInfo,
  PluginActionInfo,
  PluginsGetResponse,
  DiscoveredPluginOption,
  ServiceDeclarationRow,
} from './plugin/types'
import { SERVICE_DECLARATION_DEFS } from './plugin/types'

defineOptions({ name: 'PluginView' })

const _logger = window.electronAPI.getLogger('插件管理')
const router = useRouter()

// ---- Composables ----
const pluginData = usePluginData()
const pluginLayout = usePluginLayout()

// ---- 解构 ----
const {
  loading,
  submitting,
  reloadingAll,
  togglingInstanceId,
  pluginActionLoadingId,
  uninstallingPlugin,
  version,
  discoveredPlugins,
  schemaMap,
  schemaErrors,
  pluginServices,
  pluginRoutes,
  pluginActions,
  pluginPackages,
  instances,
  runtimeStates,
  applySnapshot,
  fetchData,
  submitEdit: submitEditApi,
  submitAdd: submitAddApi,
  deleteInstance: deleteInstanceApi,
  reloadAll: reloadAllApi,
  reloadInstance: reloadInstanceApi,
  reloadPlugin: reloadPluginApi,
  uninstallPluginPackage: uninstallPluginPackageApi,
  toggleInstanceEnabled,
  runDeclaredPluginAction,
  subscribe,
  unsubscribe,
  handlePluginSystemMessage,
  cleanup,
} = pluginData

// ---- 本地状态 ----
const keyword = ref('')
const addPluginKeyword = ref('')
const selectedInstanceId = ref('')
const editSnapshot = ref('')
const schemaFieldErrors = ref<Record<string, string>>({})
const addModalVisible = ref(false)
const jsonPreviewVisible = ref(false)
const sensitiveDirty = ref(false)
const pluginInstanceDetailRef = ref<InstanceType<typeof PluginInstanceDetail> | null>(null)
let pluginSystemSubscriptionId = ''

// ---- 表单 ----
const addForm = reactive({ plugin: '', name: '', enabled: true })
const editForm = reactive({
  instanceId: '',
  plugin: '',
  name: '',
  enabled: true,
  configText: '{}',
})

// ---- 计算属性 ----

const selectedInstance = computed<PluginInstance | null>(
  () => instances.value.find(item => item.id === selectedInstanceId.value) ?? null
)

const selectedRuntimeState = computed(() => {
  if (!selectedInstanceId.value) return null
  return runtimeStates.value[selectedInstanceId.value] || null
})

const activeInstanceCount = computed(
  () =>
    instances.value.filter(
      instance => instance.enabled && runtimeStates.value[instance.id]?.status === 'active'
    ).length
)

const selectedPluginService = computed(() => {
  const pluginName = editForm.plugin || selectedInstance.value?.plugin
  if (!pluginName) return null
  return pluginServices.value[pluginName] || null
})

const selectedPluginPackage = computed(() => {
  const pluginName = editForm.plugin || selectedInstance.value?.plugin
  if (!pluginName) return null
  return pluginPackages.value[pluginName] || null
})

const selectedPluginPackageName = computed(() => selectedPluginPackage.value?.package || '')
const canUninstallSelectedPlugin = computed(
  () => Boolean(selectedPluginPackageName.value) && !selectedInstance.value?.locked
)

const activeSchema = computed(() => {
  const pluginName = editForm.plugin || selectedInstance.value?.plugin
  if (!pluginName) return {}
  return schemaMap.value[pluginName] || {}
})

const activeSchemaEntries = computed(() =>
  Object.entries(activeSchema.value).filter(([field, fieldSchema]) => {
    if (field === 'enable' && isBooleanSchema(fieldSchema)) return false
    return true
  })
)

const hiddenSchemaFields = computed(() => {
  const fields: string[] = []
  if (activeSchema.value.enable && isBooleanSchema(activeSchema.value.enable)) {
    fields.push('enable')
  }
  return fields
})

const currentSchemaError = computed(() => {
  if (!editForm.plugin) return ''
  return schemaErrors.value[editForm.plugin] || ''
})

const selectedPluginActions = computed(() => {
  if (!selectedInstanceId.value) return [] as PluginActionInfo[]
  return pluginActions.value[selectedInstanceId.value] || []
})

const isDirty = computed(() => {
  if (!selectedInstance.value) return false
  if (sensitiveDirty.value) return true
  const current = JSON.stringify({
    instanceId: editForm.instanceId,
    plugin: editForm.plugin,
    name: editForm.name,
    enabled: editForm.enabled,
    configText: editForm.configText,
  })
  return current !== editSnapshot.value
})

const jsonPreviewText = computed(() => {
  try {
    return JSON.stringify(parseConfigText(editForm.configText), null, 2)
  } catch {
    return editForm.configText
  }
})

// ---- 插件发现选项 ----

const sortedDiscoveredPlugins = computed(() =>
  [...discoveredPlugins.value].sort((left, right) => left.localeCompare(right, 'zh-Hans-CN'))
)

const pluginInstanceCountMap = computed(() => {
  const counts: Record<string, number> = {}
  for (const item of instances.value) {
    counts[item.plugin] = (counts[item.plugin] || 0) + 1
  }
  return counts
})

const systemPluginNames = computed(
  () => new Set(instances.value.filter(item => item.system).map(item => item.plugin))
)

const getPluginServiceCount = (pluginName: string) => {
  const service = pluginServices.value[pluginName]
  if (!service) return 0
  return ['provides', 'needs', 'wants'].reduce((total, key) => {
    const values = service[key as keyof PluginServiceInfo]
    return total + (Array.isArray(values) ? values.length : 0)
  }, 0)
}

const getPluginRouteCount = (pluginName: string) => {
  const routes = pluginRoutes.value[pluginName]
  return Array.isArray(routes) ? routes.length : 0
}

const buildPluginSearchText = (pluginName: string) => {
  const service = pluginServices.value[pluginName]
  const routes = pluginRoutes.value[pluginName] || []
  const values = [
    pluginName,
    ...(service?.provides || []),
    ...(service?.needs || []),
    ...(service?.wants || []),
    ...routes.flatMap(route => [route.kind, route.path, ...(route.methods || [])]),
    schemaErrors.value[pluginName] || '',
  ]
  return values.join(' ').toLowerCase()
}

const hasServiceListItems = (items?: string[]) => Array.isArray(items) && items.length > 0

const getServiceDeclarationRows = (service?: PluginServiceInfo | null): ServiceDeclarationRow[] => {
  if (!service) return []
  return SERVICE_DECLARATION_DEFS.map((item): ServiceDeclarationRow | null => {
    const values = service[item.key]
    if (!hasServiceListItems(values)) return null
    return { key: item.key, label: item.label, color: item.color, value: values.join('、') }
  }).filter((item): item is ServiceDeclarationRow => item !== null)
}

const buildPluginOptionDescription = (pluginName: string) => {
  const serviceRows = getServiceDeclarationRows(pluginServices.value[pluginName] || null)
  if (serviceRows.length > 0) {
    return serviceRows.map(row => `${row.label}：${row.value}`).join(' · ')
  }
  const routes = pluginRoutes.value[pluginName] || []
  if (routes.length > 0) {
    return routes
      .slice(0, 2)
      .map(route => `${route.kind.toUpperCase()} ${route.path}`)
      .join(' · ')
  }
  if (schemaErrors.value[pluginName]) return schemaErrors.value[pluginName]
  return '未声明额外服务或路由信息'
}

const discoveredPluginOptions = computed<DiscoveredPluginOption[]>(() =>
  sortedDiscoveredPlugins.value
    .filter(name => !systemPluginNames.value.has(name))
    .map(name => ({
      name,
      instanceCount: pluginInstanceCountMap.value[name] || 0,
      serviceCount: getPluginServiceCount(name),
      routeCount: getPluginRouteCount(name),
      schemaError: schemaErrors.value[name] || '',
      description: buildPluginOptionDescription(name),
      searchText: buildPluginSearchText(name),
    }))
)

const filteredDiscoveredPluginOptions = computed(() => {
  const kw = addPluginKeyword.value.trim().toLowerCase()
  if (!kw) return discoveredPluginOptions.value
  return discoveredPluginOptions.value.filter(item => item.searchText.includes(kw))
})

const selectedAddPluginOption = computed(() => {
  if (!addForm.plugin) return null
  return (
    discoveredPluginOptions.value.find(item => item.name === addForm.plugin) || {
      name: addForm.plugin,
      instanceCount: pluginInstanceCountMap.value[addForm.plugin] || 0,
      serviceCount: getPluginServiceCount(addForm.plugin),
      routeCount: getPluginRouteCount(addForm.plugin),
      schemaError: schemaErrors.value[addForm.plugin] || '',
      description: buildPluginOptionDescription(addForm.plugin),
      searchText: buildPluginSearchText(addForm.plugin),
    }
  )
})

const selectedAddPluginServiceRows = computed(() =>
  getServiceDeclarationRows(pluginServices.value[addForm.plugin] || null)
)

// ---- 实例排序 ----

const orderedInstances = computed(() => {
  const orderIndexMap = new Map<string, number>()
  pluginLayout.layout.value.instanceOrder.forEach((instanceId, index) => {
    orderIndexMap.set(instanceId, index)
  })
  return [...instances.value].sort((left, right) => {
    const leftIndex = orderIndexMap.get(left.id)
    const rightIndex = orderIndexMap.get(right.id)
    if (leftIndex == null && rightIndex == null) return 0
    if (leftIndex == null) return 1
    if (rightIndex == null) return -1
    return leftIndex - rightIndex
  })
})

const filteredInstances = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return orderedInstances.value
  return orderedInstances.value.filter(item => {
    return (
      item.id.toLowerCase().includes(kw) ||
      item.plugin.toLowerCase().includes(kw) ||
      (item.name || '').toLowerCase().includes(kw)
    )
  })
})

// ---- 编辑快照 ----

const captureEditSnapshot = () =>
  JSON.stringify({
    instanceId: editForm.instanceId,
    plugin: editForm.plugin,
    name: editForm.name,
    enabled: editForm.enabled,
    configText: editForm.configText,
  })

const setEditFromInstance = (row: PluginInstance) => {
  pluginInstanceDetailRef.value?.resetSensitiveDrafts()
  sensitiveDirty.value = false
  editForm.instanceId = row.id
  editForm.plugin = row.plugin
  editForm.name = row.name
  editForm.enabled = row.enabled
  const nextConfig = { ...(row.config || {}) }
  if (checkHasEnableSchema(row.plugin, schemaMap.value)) {
    nextConfig.enable = row.enabled
  }
  editForm.configText = JSON.stringify(nextConfig, null, 2)
  refreshSchemaFieldErrors()
  editSnapshot.value = captureEditSnapshot()
}

const refreshSchemaFieldErrors = () => {
  schemaFieldErrors.value = collectSchemaFieldErrors(activeSchemaEntries.value, editForm.configText)
}

const handleSchemaValidationChange = (errors: Record<string, string>) => {
  schemaFieldErrors.value = errors
}

// ---- 快照应用 ----

const applySnapshotWithLayout = (data: PluginsGetResponse) => {
  const newId = applySnapshot(
    data,
    nextInstances => pluginLayout.syncWithInstances(nextInstances),
    selectedInstanceId.value
  )
  if (newId) {
    selectedInstanceId.value = newId
    const target = instances.value.find(item => item.id === newId)
    if (target) {
      setEditFromInstance(target)
    }
  } else {
    selectedInstanceId.value = ''
  }
  return newId
}

// ---- 选择实例 ----

const applyInstanceSelection = (instanceId: string) => {
  selectedInstanceId.value = instanceId
  const target = instances.value.find(item => item.id === instanceId)
  if (target) {
    setEditFromInstance(target)
  }
}

const selectInstance = (instanceId: string) => {
  if (selectedInstanceId.value && instanceId !== selectedInstanceId.value && isDirty.value) {
    Modal.confirm({
      title: '放弃未保存改动？',
      content: '切换插件实例会丢弃当前尚未保存的配置改动。',
      okText: '放弃并切换',
      cancelText: '继续编辑',
      onOk: () => applyInstanceSelection(instanceId),
    })
    return
  }
  applyInstanceSelection(instanceId)
}

// ---- 操作 ----

const handleRefresh = async () => {
  const newId = await fetchData(applySnapshotWithLayout)
  if (newId) {
    selectedInstanceId.value = newId
    const target = instances.value.find(item => item.id === newId)
    if (target) setEditFromInstance(target)
  }
}

// ---- 插件获取 / 右键菜单处理 ----

const openPluginMarket = () => {
  void router.push('/plugins-market')
}

const handleOpenPluginDir = async (instance: PluginInstance) => {
  const pkg = pluginPackages.value[instance.plugin]
  const pluginPath = pkg?.path || ''
  if (!pluginPath) {
    message.info(`插件 ${instance.plugin} 未暴露目录路径`)
    return
  }
  const result = (await window.electronAPI.showItemInFolder(pluginPath)) as unknown as {
    success?: boolean
    error?: string
  }
  if (result?.success === false) {
    message.error(`打开插件目录失败: ${result.error || '未知错误'}`)
  }
}

const handleCheckUpdate = (instance: PluginInstance) => {
  message.info(`请在插件市场查看 ${instance.plugin} 的可用版本`)
  openPluginMarket()
}

const handleUninstallInstance = (instance: PluginInstance) => {
  if (instance.locked) {
    message.info('系统插件不可卸载')
    return
  }
  Modal.confirm({
    title: '卸载插件包',
    content: `确认卸载插件包 ${instance.plugin}？相关实例配置不会自动删除。`,
    okText: '卸载',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => handleUninstallPlugin(instance.plugin),
  })
}

const openAddModal = () => {
  addForm.plugin = discoveredPluginOptions.value[0]?.name || ''
  addForm.name = ''
  addForm.enabled = true
  addPluginKeyword.value = ''
  addModalVisible.value = true
}

const submitAdd = async () => {
  if (!addForm.plugin) {
    message.warning('请先选择要新增的插件')
    return
  }
  const newId = await submitAddApi({
    plugin: addForm.plugin,
    name: addForm.name || undefined,
    enabled: addForm.enabled,
  })
  if (newId) {
    addModalVisible.value = false
    if (instances.value.some(item => item.id === newId)) {
      selectInstance(newId)
    } else {
      selectedInstanceId.value = newId
    }
  }
}

const resetEdit = () => {
  const target = selectedInstance.value
  if (!target) return
  pluginInstanceDetailRef.value?.resetSensitiveDrafts()
  sensitiveDirty.value = false
  setEditFromInstance(target)
}

const mergeConfigPatch = (
  base: Record<string, unknown>,
  patch: Record<string, unknown>
): Record<string, unknown> => {
  const merged = structuredClone(base)
  Object.entries(patch).forEach(([key, value]) => {
    const current = merged[key]
    if (
      current &&
      typeof current === 'object' &&
      !Array.isArray(current) &&
      value &&
      typeof value === 'object' &&
      !Array.isArray(value)
    ) {
      merged[key] = mergeConfigPatch(
        current as Record<string, unknown>,
        value as Record<string, unknown>
      )
    } else {
      merged[key] = structuredClone(value)
    }
  })
  return merged
}

const validateActiveSchemaBeforeSubmit = () => {
  const errors = pluginInstanceDetailRef.value?.validateSchema() ?? schemaFieldErrors.value
  const [firstError] = Object.entries(errors)
  if (!firstError) return

  const [field, error] = firstError
  throw new Error(
    `${getFieldLabel(field, activeSchema.value[field] || { type: 'string' })}: ${error}`
  )
}

const submitEdit = async (configPatch?: Record<string, unknown>) => {
  let config: Record<string, unknown>
  try {
    config = configPatch ?? parseConfigText(editForm.configText)
    validateActiveSchemaBeforeSubmit()
  } catch (error) {
    message.error(`更新失败: ${String(error)}`)
    return
  }
  if (checkHasEnableSchema(editForm.plugin, schemaMap.value)) {
    config.enable = editForm.enabled
  }
  const target = selectedInstance.value
  if (!target) {
    message.error('未选择插件实例')
    return
  }
  const payload: Record<string, unknown> = { instanceId: editForm.instanceId }
  if (editForm.name !== target.name) payload.name = editForm.name
  if (editForm.plugin !== target.plugin) payload.plugin = editForm.plugin
  if (editForm.enabled !== target.enabled) payload.enabled = editForm.enabled
  const targetConfig = { ...(target.config || {}) }
  if (checkHasEnableSchema(editForm.plugin, schemaMap.value)) {
    targetConfig.enable = target.enabled
  }
  const nextConfig = mergeConfigPatch(targetConfig, config)
  const nextConfigText = JSON.stringify(nextConfig, null, 2)
  if (JSON.stringify(config, null, 2) !== JSON.stringify(targetConfig, null, 2)) {
    payload.config = config
  }
  const success = await submitEditApi(payload, rawError =>
    sanitizeErrorForLog(
      sanitizeErrorForLog(rawError, nextConfig, activeSchema.value as any),
      targetConfig,
      activeSchema.value as any
    )
  )
  if (success) {
    instances.value = instances.value.map(item =>
      item.id === editForm.instanceId
        ? {
            ...item,
            plugin: editForm.plugin,
            name: editForm.name,
            enabled: editForm.enabled,
            config: nextConfig,
          }
        : item
    )
    editForm.configText = nextConfigText
    pluginInstanceDetailRef.value?.resetSensitiveDrafts()
    sensitiveDirty.value = false
    editSnapshot.value = captureEditSnapshot()
  }
}

const handleDeleteInstance = async (instanceId: string) => {
  const target = instances.value.find(item => item.id === instanceId)
  if (target?.locked) {
    message.info('系统插件不可删除')
    return
  }
  const success = await deleteInstanceApi(instanceId)
  if (success) {
    const nextInstances = instances.value.filter(item => item.id !== instanceId)
    instances.value = nextInstances
    pluginLayout.syncWithInstances(nextInstances)
    if (selectedInstanceId.value === instanceId) {
      const nextSelectedId = nextInstances[0]?.id || ''
      selectedInstanceId.value = nextSelectedId
      const nextSelectedInstance = nextInstances.find(item => item.id === nextSelectedId)
      if (nextSelectedInstance) setEditFromInstance(nextSelectedInstance)
    }
  }
}

const handleReloadAll = () => reloadAllApi()

const handleReloadInstance = (instanceId: string) => reloadInstanceApi(instanceId)

const handleReloadPlugin = (plugin: string) => reloadPluginApi(plugin)

const handleUninstallPlugin = async (plugin: string) => {
  if (selectedInstance.value?.locked) {
    message.info('系统插件不可卸载')
    return
  }
  const packageName = pluginPackages.value[plugin]?.package || ''
  if (!packageName) {
    message.warning('当前插件缺少安装包信息，无法卸载')
    return
  }
  const success = await uninstallPluginPackageApi(plugin, packageName)
  if (success) {
    await handleRefresh()
  }
}

const handleToggleEnabled = async (instance: PluginInstance, enabled: boolean) => {
  const success = await toggleInstanceEnabled(instance, enabled)
  if (success) {
    instances.value = instances.value.map(item =>
      item.id === instance.id ? { ...item, enabled } : item
    )
    if (selectedInstanceId.value === instance.id && !isDirty.value) {
      editForm.enabled = enabled
      if (checkHasEnableSchema(editForm.plugin, schemaMap.value)) {
        try {
          const config = parseConfigText(editForm.configText)
          config.enable = enabled
          editForm.configText = setConfigObjectToText(config)
        } catch {
          // 忽略
        }
      }
      editSnapshot.value = captureEditSnapshot()
    }
  }
}

const handleTriggerAction = (action: PluginActionInfo) => {
  runDeclaredPluginAction(action, '插件动作', () => handleRefresh())
}

const handleTriggerSchemaAction = (field: string, fieldSchema: PluginSchemaField) => {
  const action = getSchemaButtonAction(field, fieldSchema, editForm.plugin)
  if (!action) {
    message.warning('Schema 按钮缺少 action.path 声明')
    return
  }
  runDeclaredPluginAction(action, 'Schema 按钮', () => handleRefresh())
}

const openJsonPreview = () => {
  jsonPreviewVisible.value = true
}

const copyDiagnostics = async () => {
  const runtime = selectedRuntimeState.value
  const parts = [
    `时间: ${new Date().toISOString()}`,
    `实例 ID: ${selectedInstanceId.value || '未选择'}`,
    `插件: ${editForm.plugin || '未知'}`,
    `运行状态: ${runtime?.status || '未知'}`,
    `生命周期: ${runtime?.lifecycle_phase || '未知'}`,
    `最近错误: ${runtime?.last_error || '无'}`,
    `重载次数: ${runtime?.reload_count ?? '未知'}`,
  ]
  try {
    await navigator.clipboard.writeText(parts.join('\n'))
    message.success('诊断信息已复制到剪贴板')
  } catch {
    message.error('复制失败')
  }
}

// ---- 拖拽 ----

const collectRenderedInstanceOrder = () => {
  const renderedIds: string[] = []
  document.querySelectorAll('.instance-group .instance-item').forEach(itemEl => {
    const element = itemEl as HTMLElement
    const instanceId = element.dataset.id
    if (instanceId) renderedIds.push(instanceId)
  })
  return renderedIds
}

const buildFullInstanceOrder = (renderedIds: string[]) => {
  const renderedSet = new Set(renderedIds)
  const currentOrderedIds = orderedInstances.value.map(item => item.id)
  return [...renderedIds, ...currentOrderedIds.filter(instanceId => !renderedSet.has(instanceId))]
}

const onDragEnd = (evt: any, _sourceGroup: string) => {
  if (evt.oldIndex === evt.newIndex && evt.from === evt.to) return
  if (keyword.value.trim().length > 0) {
    message.warning('搜索筛选中不支持拖拽排序，请先清空搜索条件')
    return
  }
  const draggedId = evt.item?.__draggable_context?.element?.id
  if (!draggedId) return

  let targetGroup = pluginLayout.getInstanceGroupKey(draggedId)
  if (evt.from !== evt.to && draggedId) {
    const targetGroupEl = evt.to.closest('.instance-group')
    targetGroup = targetGroupEl?.dataset?.group ?? ''
  }

  const renderedIds = collectRenderedInstanceOrder()
  if (renderedIds.length === 0) return

  pluginLayout.updateLayout(draft => {
    draft.instanceOrder = buildFullInstanceOrder(renderedIds)
    if (targetGroup) {
      draft.instanceGroups[draggedId] = targetGroup
      if (!draft.groupOrder.includes(targetGroup)) {
        draft.groupOrder.push(targetGroup)
      }
    } else {
      delete draft.instanceGroups[draggedId]
    }
  })
}

const createGroup = () => {
  let name = ''
  Modal.confirm({
    title: '新建分组',
    content: h('div', [
      h(Input, {
        placeholder: '请输入分组名称',
        onChange: (e: any) => {
          name = e.target?.value ?? e
        },
      }),
    ]),
    onOk: async () => {
      const trimmed = (name || '').trim()
      if (!trimmed) {
        message.warning('分组名称不能为空')
        return
      }
      if (pluginLayout.layout.value.groupOrder.includes(trimmed)) {
        message.warning(`分组 "${trimmed}" 已存在`)
        return
      }
      pluginLayout.updateLayout(draft => {
        draft.groupOrder.push(trimmed)
      })
      message.success(`分组 "${trimmed}" 已创建，可通过拖拽移动实例到该分组`)
    },
  })
}

const handleGroupAction = (action: string, groupKey: string) => {
  if (action === 'rename') {
    let newName = groupKey
    Modal.confirm({
      title: '重命名分组',
      content: h('div', [
        h(Input, {
          defaultValue: groupKey,
          onChange: (e: any) => {
            newName = e.target?.value ?? e
          },
        }),
      ]),
      onOk: async () => {
        const trimmed = (newName || '').trim()
        if (!trimmed || trimmed === groupKey) return
        if (pluginLayout.layout.value.groupOrder.includes(trimmed)) {
          message.warning(`分组 "${trimmed}" 已存在`)
          return
        }
        pluginLayout.updateLayout(draft => {
          draft.groupOrder = draft.groupOrder.map(group => (group === groupKey ? trimmed : group))
          for (const [instanceId, group] of Object.entries(draft.instanceGroups)) {
            if (group === groupKey) draft.instanceGroups[instanceId] = trimmed
          }
        })
        message.success(`分组已重命名为 "${trimmed}"`)
      },
    })
  } else if (action === 'delete') {
    pluginLayout.updateLayout(draft => {
      draft.groupOrder = draft.groupOrder.filter(group => group !== groupKey)
      for (const [instanceId, group] of Object.entries(draft.instanceGroups)) {
        if (group === groupKey) delete draft.instanceGroups[instanceId]
      }
    })
    message.success(`分组 "${groupKey}" 已删除，实例已移回默认分组`)
  }
}

// ---- 生命周期 ----

const handleWsMessage = (wsMessage: any) => {
  const newId = handlePluginSystemMessage(
    wsMessage,
    (data, preferredId) => {
      // 自定义 applySnapshot 包装
      const resultId = applySnapshot(
        data,
        nextInstances => pluginLayout.syncWithInstances(nextInstances),
        preferredId
      )
      if (resultId) {
        selectedInstanceId.value = resultId
        const target = instances.value.find(item => item.id === resultId)
        if (target) setEditFromInstance(target)
      }
      return resultId
    },
    selectedInstanceId.value
  )
  if (newId) {
    selectedInstanceId.value = newId
    const target = instances.value.find(item => item.id === newId)
    if (target) setEditFromInstance(target)
  }
}

watch(
  [() => editForm.configText, () => editForm.plugin, activeSchemaEntries],
  () => refreshSchemaFieldErrors(),
  { deep: true, flush: 'post' }
)

onMounted(() => {
  pluginSystemSubscriptionId = subscribe({ id: 'PluginSystem' }, handleWsMessage)
  void handleRefresh()
})

onUnmounted(() => {
  if (pluginSystemSubscriptionId) {
    unsubscribe(pluginSystemSubscriptionId)
    pluginSystemSubscriptionId = ''
  }
  cleanup()
})
</script>

<style scoped>
.plugin-page {
  height: 100%;
  min-height: 0;
  min-width: 0;
  container: plugin-page / inline-size;
  box-sizing: border-box;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--v6-color-window);
  color: var(--v6-color-text);
}

.plugin-page-header,
.plugin-toolbar {
  flex-shrink: 0;
}

.plugin-summary {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  white-space: nowrap;
}

.toolbar-hint {
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
}

.toolbar-search {
  width: 180px;
}

.toolbar-search :deep(.anticon) {
  color: var(--v6-color-text-tertiary);
  font-size: 13px;
}

/* 无边界分栏：内容直接铺在窗体背景上，仅保留双 pane 分隔线（拒绝白框套白框） */
.plugin-workspace {
  --plugin-instance-list-width: 380px;
  display: grid;
  grid-template-columns: var(--plugin-instance-list-width) minmax(0, 1fr);
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  margin: var(--v6-space-4) var(--v6-content-padding-inline)
    calc(var(--v6-space-6) + var(--v6-space-2));
}

.plugin-list-pane,
.plugin-detail-pane {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.plugin-list-pane {
  border-right: 1px solid var(--v6-color-border);
}

/* .plugin-page 自身规则须由外层 app-shell 的 app-content 容器驱动
   (@container 不能命中声明容器的元素自身) */
@container app-content (max-width: 760px) {
  .plugin-page {
    overflow: auto;
  }
}

@container plugin-page (max-width: 760px) {
  .plugin-workspace {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(240px, 38vh) minmax(360px, 1fr);
    min-height: 680px;
    overflow: visible;
    margin-inline: var(--v6-space-3);
  }

  .plugin-list-pane {
    border-right: none;
    border-bottom: 1px solid var(--v6-color-border);
  }

  .plugin-list-pane,
  .plugin-detail-pane {
    overflow: auto;
  }

  .toolbar-search {
    width: min(220px, 48vw);
  }
}
@container plugin-page (max-width: 920px) {
  .plugin-workspace {
    --plugin-instance-list-width: 320px;
  }

  .toolbar-hint {
    display: none;
  }
}
</style>
