<template>
  <div class="user-edit-page">
    <PageHeader
      :title="userName || (isEdit ? '编辑插件用户' : '创建插件用户')"
      :subtitle="scriptName ? `${scriptName} · 插件用户配置` : '插件用户配置'"
      :bordered="false"
      compact
      transparent
    >
      <a-space :size="6" wrap>
        <a-tag :color="getScriptTypeTagColor(scriptType, scriptThemeColor)">
          {{ scriptDisplayName || '插件脚本' }}
        </a-tag>
        <a-tag v-for="mode in supportedModes" :key="mode" color="blue">
          {{ modeLabels[mode] || mode }}
        </a-tag>
      </a-space>
      <template #actions>
        <HeaderSchemaActionButton
          v-for="action in headerSchemaActions"
          :key="action.key"
          :action="action"
          :loading="actionLoadingId === action.key"
          @click="handleFieldAction(action.key, action.field)"
        />
        <a-button v-if="docsUrl" :href="docsUrl" target="_blank">查看文档</a-button>
        <a-button type="primary" :loading="saving" @click="handleSave">保存配置</a-button>
        <a-button @click="router.push('/scripts')">返回</a-button>
      </template>
    </PageHeader>

    <main class="user-edit-content">
      <a-spin :spinning="loading" tip="加载插件用户配置中...">
        <section class="user-edit-surface">
          <a-alert
            v-if="saveError"
            class="save-error"
            type="error"
            show-icon
            :message="saveError"
          />
          <SchemaForm
            v-if="userSchema"
            ref="schemaFormRef"
            v-model="formModel"
            :schema="userSchema"
            :hide-fields="headerSchemaActionKeys"
            :action-loading-id="actionLoadingId"
            @trigger-action="({ field, fieldSchema }) => handleFieldAction(field, fieldSchema)"
            @validation-change="errors => (fieldErrors = errors)"
          />
          <a-empty v-else-if="!loading" description="此插件脚本类型未提供用户配置表单" />

          <section v-if="pluginConfigEditor && userId" class="embedded-config-editor">
            <PluginJsonConfigEditor
              :script-id="scriptId"
              :user-id="userId"
              :endpoint-prefix="pluginConfigEditor.endpointPrefix"
              :title="pluginConfigEditor.title"
            />
          </section>
        </section>
      </a-spin>
    </main>

    <SchemaActionSessionMask
      :visible="sessionVisible"
      :title="sessionTitle"
      :description="sessionDescription"
      :stop-label="sessionStopLabel"
      :stopping="sessionStopping"
      @stop="stopActiveSession()"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import HeaderSchemaActionButton from '@/components/HeaderSchemaActionButton.vue'
import PageHeader from '@/components/mac/PageHeader.vue'
import SchemaForm from '@/components/SchemaForm.vue'
import SchemaActionSessionMask from '@/components/SchemaActionSessionMask.vue'
import PluginJsonConfigEditor from '@/views/OkScriptUserEdit/OkScriptConfigEditor.vue'
import { useSchemaActionRunner } from '@/composables/useSchemaActionRunner'
import {
  buildSchemaSavePayload,
  sanitizeErrorForLog,
} from '@/composables/useSensitiveFieldStrategy'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import type {
  SchemaDefinition,
  SchemaFieldDefinition,
  SchemaValidationErrorMap,
} from '@/types/schemaForm'
import {
  descriptorMapFromList,
  getScriptTypeTagColor,
  normalizeScriptRecord,
} from '@/utils/scriptRegistry'
import { collectHeaderSchemaActions } from '@/utils/schemaActions'

const logger = window.electronAPI.getLogger('插件用户编辑')

const route = useRoute()
const router = useRouter()
const api = useScriptRegistryApi()
const { subscribe, unsubscribe } = useWebSocket()

const loading = ref(true)
const saving = ref(false)
const saveError = ref('')
const fieldErrors = ref<SchemaValidationErrorMap>({})
const schemaFormRef = ref<InstanceType<typeof SchemaForm> | null>(null)
const schemaRefreshInFlight = ref(false)

const scriptId = route.params.scriptId as string
const routeUserId = route.params.userId as string | undefined
const isEdit = ref(Boolean(routeUserId))
const userId = ref(routeUserId || '')
const scriptName = ref('')
const userName = ref('')
const scriptType = ref('')
const scriptEditorKind = ref('')
const scriptThemeColor = ref<string | null>(null)
const scriptDisplayName = ref('')
const docsUrl = ref<string | null>(null)
const supportedModes = ref<string[]>([])
const descriptorClient = ref<Record<string, unknown>>({})
const userSchema = ref<SchemaDefinition | null>(null)
const formModel = ref<Record<string, any>>({})
const headerSchemaActions = computed(() => collectHeaderSchemaActions(userSchema.value))
const headerSchemaActionKeys = computed(() => headerSchemaActions.value.map(action => action.key))
let pluginSystemSubscriptionId: string | null = null

interface PluginSystemSnapshotMessage {
  kind: 'snapshot'
}

interface PluginSystemHmrMessage {
  kind: 'hmr'
  plugin?: string | null
  status: 'running' | 'success' | 'error' | string
  message?: string
}

interface PluginConfigEditorDeclaration {
  endpointPrefix: string
  title?: string
}

const modeLabels: Record<string, string> = {
  AutoProxy: '全自动代理',
  ManualReview: '人工审核',
  ScriptConfig: '脚本配置',
}

const displayNameFromForm = computed(() => {
  const info = formModel.value?.Info
  if (typeof info?.Name === 'string' && info.Name.trim()) {
    return info.Name
  }
  if (typeof formModel.value?.user_name === 'string' && formModel.value.user_name.trim()) {
    return formModel.value.user_name
  }
  if (typeof formModel.value?.name === 'string' && formModel.value.name.trim()) {
    return formModel.value.name
  }
  return ''
})

const cloneValue = <T,>(value: T): T => JSON.parse(JSON.stringify(value))

const normalizePluginKey = (value?: string | null) =>
  String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')

const currentPluginKey = () => {
  const editorKind = scriptEditorKind.value || ''
  if (!editorKind.startsWith('plugin:')) {
    return ''
  }
  return normalizePluginKey(editorKind.slice('plugin:'.length))
}

const pluginConfigEditor = computed<PluginConfigEditorDeclaration | null>(() => {
  const candidate = descriptorClient.value.config_editor
  if (!candidate || typeof candidate !== 'object') return null

  const config = candidate as Record<string, unknown>
  if (config.kind !== 'json-files' || typeof config.endpoint_prefix !== 'string') return null

  return {
    endpointPrefix: config.endpoint_prefix,
    title: typeof config.title === 'string' ? config.title : undefined,
  }
})

const isCurrentPluginEvent = (plugin?: string | null) => {
  const key = currentPluginKey()
  if (!key) {
    return false
  }
  if (!plugin) {
    return true
  }
  return normalizePluginKey(plugin) === key
}

const loadData = async ({
  preserveFormModel = false,
  redirectOnError = true,
  showError = true,
}: {
  preserveFormModel?: boolean
  redirectOnError?: boolean
  showError?: boolean
} = {}) => {
  loading.value = true
  const preservedFormModel = preserveFormModel ? cloneValue(formModel.value || {}) : null
  try {
    const [descriptors, scripts] = await Promise.all([
      api.getScriptTypes(),
      api.getScripts(scriptId),
    ])
    const scriptRecord = scripts[0]
    if (!scriptRecord) {
      throw new Error('脚本不存在')
    }

    const descriptorMap = descriptorMapFromList(descriptors)
    const normalizedScript = normalizeScriptRecord(scriptRecord, descriptorMap, [])
    if (normalizedScript.available === false) {
      throw new Error(
        normalizedScript.unavailableReason || `脚本类型 ${normalizedScript.type} 当前未启用`
      )
    }

    const descriptor = descriptorMap[scriptRecord.type]
    scriptName.value = normalizedScript.name
    scriptType.value = normalizedScript.type
    scriptEditorKind.value = normalizedScript.editorKind || ''
    scriptThemeColor.value = normalizedScript.themeColor || null
    scriptDisplayName.value = normalizedScript.displayName || normalizedScript.type
    docsUrl.value = normalizedScript.docsUrl || null
    supportedModes.value = normalizedScript.supportedModes || []
    descriptorClient.value = descriptor?.client || {}
    userSchema.value = descriptor?.user_schema || null

    if (!userId.value) {
      const created = await api.addUser(scriptId)
      userId.value = created.id
      isEdit.value = true
      router.replace(`/scripts/${scriptId}/users/${created.id}/edit/plugin`)
    }

    const users = await api.getUsers(scriptId, userId.value)
    const user = users[0]
    if (!user) {
      throw new Error('用户不存在')
    }

    userName.value = user.name
    userSchema.value = user.schema || descriptor?.user_schema || null
    formModel.value = preservedFormModel ?? cloneValue(user.config || {})
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载插件用户失败: ${errorMsg}`)
    if (showError) {
      message.error(errorMsg)
    }
    if (redirectOnError) {
      router.push('/scripts')
    }
  } finally {
    loading.value = false
  }
}

const refreshSchemaFromPluginSystem = async () => {
  if (loading.value || schemaRefreshInFlight.value || !currentPluginKey()) {
    return
  }
  schemaRefreshInFlight.value = true
  try {
    await loadData({
      preserveFormModel: true,
      redirectOnError: false,
      showError: false,
    })
  } finally {
    schemaRefreshInFlight.value = false
  }
}

const refreshImportedInfrastructure = async () => {
  const preservedFormModel = cloneValue(formModel.value || {})
  const [descriptors, users] = await Promise.all([
    api.getScriptTypes(),
    api.getUsers(scriptId, userId.value),
  ])
  const descriptorMap = descriptorMapFromList(descriptors)
  const descriptor = descriptorMap[scriptType.value]
  const user = users[0]
  if (!user) {
    throw new Error('用户不存在')
  }

  const latestConfig = cloneValue(user.config || {})
  userSchema.value = user.schema || descriptor?.user_schema || null

  const nextFormModel = {
    ...preservedFormModel,
    Info: {
      ...(preservedFormModel.Info || {}),
      InfrastName: latestConfig?.Info?.InfrastName ?? preservedFormModel?.Info?.InfrastName,
      InfrastIndex: latestConfig?.Info?.InfrastIndex ?? preservedFormModel?.Info?.InfrastIndex,
    },
    Data: {
      ...(preservedFormModel.Data || {}),
      CustomInfrast: latestConfig?.Data?.CustomInfrast ?? preservedFormModel?.Data?.CustomInfrast,
    },
  }

  formModel.value = nextFormModel
}

const handlePluginSystemMessage = (wsMessage: WebSocketBaseMessage) => {
  const payload = wsMessage.data as PluginSystemSnapshotMessage | PluginSystemHmrMessage | undefined
  if (!payload || typeof payload !== 'object') {
    return
  }

  if (payload.kind === 'snapshot') {
    void refreshSchemaFromPluginSystem()
    return
  }

  if (
    payload.kind === 'hmr' &&
    payload.status === 'error' &&
    isCurrentPluginEvent(payload.plugin)
  ) {
    message.warning(payload.message || `plugin hmr failed: ${payload.plugin || 'unknown'}`)
  }
}

const {
  actionLoadingId,
  sessionVisible,
  sessionTitle,
  sessionDescription,
  sessionStopLabel,
  sessionStopping,
  runFieldAction,
  stopActiveSession,
} = useSchemaActionRunner({
  onRefresh: async () => {
    await loadData()
  },
  onActionSuccess: async ({ field, action }) => {
    if (
      field !== 'Data.ImportCustomInfrast' ||
      action.path !== '/api/scripts/user/infrastructure'
    ) {
      return false
    }
    await refreshImportedInfrastructure()
    return true
  },
})

const handleFieldAction = async (field: string, fieldSchema: SchemaFieldDefinition) => {
  await runFieldAction(field, fieldSchema, {
    scriptId,
    scriptName: scriptName.value,
    scriptType: scriptType.value,
    scriptDisplayName: scriptDisplayName.value,
    userId: userId.value,
    userName: displayNameFromForm.value || userName.value,
    docsUrl: docsUrl.value,
    supportedModes: supportedModes.value,
    formModel: formModel.value,
  })
}

const handleSave = async () => {
  const result = schemaFormRef.value?.validate()
  if (result && !result.valid) {
    message.error('请先修正表单校验错误')
    return
  }

  const schema = userSchema.value || {}
  const payload =
    schemaFormRef.value?.buildSavePayload() ?? buildSchemaSavePayload(formModel.value, schema, {})
  saving.value = true
  saveError.value = ''
  try {
    const updateResult: unknown = await api.updateUser(scriptId, userId.value, payload)
    if (updateResult === false) {
      throw new Error('插件用户配置保存失败')
    }
    schemaFormRef.value?.resetSensitiveDrafts()
    await loadData()
    message.success('用户配置已保存')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    const safeError = sanitizeErrorForLog(
      sanitizeErrorForLog(errorMsg, payload, schema),
      formModel.value,
      schema
    )
    logger.error(`保存插件用户失败: ${safeError}`)
    saveError.value = safeError
    message.error(safeError)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  pluginSystemSubscriptionId = subscribe({ id: 'PluginSystem' }, handlePluginSystemMessage)
  void loadData()
})

onUnmounted(() => {
  if (pluginSystemSubscriptionId) {
    unsubscribe(pluginSystemSubscriptionId)
    pluginSystemSubscriptionId = null
  }
})
</script>

<style scoped>
.user-edit-page {
  min-height: 100%;
}

.user-edit-content {
  width: min(100%, 1280px);
  margin: 0 auto;
  padding: 0 var(--v6-content-padding-inline) var(--v6-space-8);
}

.user-edit-surface {
  min-height: 240px;
  padding: var(--v6-space-5);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-material);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.save-error {
  margin-bottom: var(--v6-space-4);
  border-radius: var(--v6-radius-control);
}

.embedded-config-editor {
  margin-top: var(--v6-space-5);
  padding-top: var(--v6-space-5);
  border-top: 1px solid var(--v6-color-border-subtle);
}

:root[data-perf-mode='low'] .user-edit-surface {
  background: var(--v6-color-surface);
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

@media (max-width: 768px) {
  .user-edit-content {
    padding-inline: var(--v6-space-4);
  }

  .user-edit-surface {
    padding: var(--v6-space-4);
  }
}
</style>
