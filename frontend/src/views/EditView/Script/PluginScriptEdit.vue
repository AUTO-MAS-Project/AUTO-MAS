<template>
  <div class="page-header">
    <div class="header-nav">
      <a-breadcrumb>
        <a-breadcrumb-item>
          <router-link to="/scripts">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>插件脚本编辑</a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <HeaderSchemaActionButton
        v-for="action in headerSchemaActions"
        :key="action.key"
        :action="action"
        :loading="actionLoadingId === action.key"
        @click="handleFieldAction(action.key, action.field)"
      />
      <a-button v-if="script?.docsUrl" :href="script.docsUrl || undefined" target="_blank">
        查看文档
      </a-button>
      <a-button type="primary" :loading="saving" :disabled="!script" @click="handleSave"
        >保存配置</a-button
      >
      <a-button @click="router.push('/scripts')">返回</a-button>
    </a-space>
  </div>

  <a-card class="config-card" :loading="loading">
    <template #title>
      <a-space>
        <img
          v-if="script && (script.icon || script.iconUrl)"
          :src="getScriptIcon(script.type, script.iconUrl)"
          alt=""
          class="script-icon"
          @error="event => handleScriptIconError(event, script?.type ?? '')"
        />
        <span>{{ script?.name || '脚本配置' }}</span>
        <a-tag :color="getScriptTypeTagColor(script?.type || '', script?.themeColor)">
          {{ script?.displayName || script?.type || '未知类型' }}
        </a-tag>
      </a-space>
    </template>

    <template #extra>
      <a-space v-if="script?.supportedModes?.length">
        <a-tag v-for="mode in script.supportedModes" :key="mode" color="blue">
          {{ modeLabels[mode] || mode }}
        </a-tag>
      </a-space>
    </template>

    <a-alert
      v-if="loadError"
      class="config-load-error"
      type="error"
      show-icon
      message="插件脚本配置加载失败"
      :description="loadError"
    >
      <template #action>
        <a-button size="small" @click="loadScript">重试</a-button>
      </template>
    </a-alert>

    <SchemaForm
      v-if="script"
      ref="schemaFormRef"
      v-model="formModel"
      :schema="script.schema || {}"
      :hide-fields="headerSchemaActionKeys"
      :action-loading-id="actionLoadingId"
      @trigger-action="({ field, fieldSchema }) => handleFieldAction(field, fieldSchema)"
      @validation-change="errors => (fieldErrors = errors)"
    />

    <a-empty v-if="script && !script.schema" description="此插件脚本类型未提供配置表单" />
  </a-card>

  <SchemaActionSessionMask
    :visible="sessionVisible"
    :title="sessionTitle"
    :description="sessionDescription"
    :stop-label="sessionStopLabel"
    :stopping="sessionStopping"
    @stop="stopActiveSession()"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import HeaderSchemaActionButton from '@/components/HeaderSchemaActionButton.vue'
import SchemaForm from '@/components/SchemaForm.vue'
import SchemaActionSessionMask from '@/components/SchemaActionSessionMask.vue'
import { useSchemaActionRunner } from '@/composables/useSchemaActionRunner'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import type { Script } from '@/types/script'
import type { SchemaFieldDefinition, SchemaValidationErrorMap } from '@/types/schemaForm'
import {
  descriptorMapFromList,
  getScriptIcon,
  getScriptTypeTagColor,
  handleScriptIconError,
  normalizeScriptRecord,
} from '@/utils/scriptRegistry'
import { collectHeaderSchemaActions } from '@/utils/schemaActions'

const logger = window.electronAPI.getLogger('插件脚本编辑')

const route = useRoute()
const router = useRouter()
const api = useScriptRegistryApi()
const { subscribe, unsubscribe } = useWebSocket()

const loading = ref(true)
const saving = ref(false)
const loadError = ref<string | null>(null)
const script = ref<Script | null>(null)
const formModel = ref<Record<string, any>>({})
const fieldErrors = ref<SchemaValidationErrorMap>({})
const schemaFormRef = ref<InstanceType<typeof SchemaForm> | null>(null)
const schemaRefreshInFlight = ref(false)
const headerSchemaActions = computed(() => collectHeaderSchemaActions(script.value?.schema || null))
const headerSchemaActionKeys = computed(() => headerSchemaActions.value.map(action => action.key))

const scriptId = route.params.id as string
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

const cloneValue = <T,>(value: T): T => JSON.parse(JSON.stringify(value))

const isPlainObject = (value: unknown): value is Record<string, any> =>
  Object.prototype.toString.call(value) === '[object Object]'

const mergeFormPatch = (
  base: Record<string, any>,
  patch: Record<string, any>
): Record<string, any> => {
  const merged = cloneValue(base)
  Object.entries(patch).forEach(([key, value]) => {
    if (isPlainObject(value) && isPlainObject(merged[key])) {
      merged[key] = mergeFormPatch(merged[key], value)
      return
    }
    merged[key] = cloneValue(value)
  })
  return merged
}

const normalizePluginKey = (value?: string | null) =>
  String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')

const currentPluginKey = () => {
  const editorKind = script.value?.editorKind || ''
  if (!editorKind.startsWith('plugin:')) {
    return ''
  }
  return normalizePluginKey(editorKind.slice('plugin:'.length))
}

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

const modeLabels: Record<string, string> = {
  AutoProxy: '全自动代理',
  ManualReview: '人工审核',
  ScriptConfig: '脚本配置',
}

const loadScript = async ({
  preserveFormModel = false,
  redirectOnError = false,
  showError = true,
}: {
  preserveFormModel?: boolean
  redirectOnError?: boolean
  showError?: boolean
} = {}) => {
  loading.value = true
  const preservedFormModel = preserveFormModel ? cloneValue(formModel.value || {}) : null
  try {
    const [descriptors, records] = await Promise.all([
      api.getScriptTypes(),
      api.getScripts(scriptId),
    ])
    const record = records[0]
    if (!record) {
      throw new Error('脚本不存在')
    }

    const descriptorMap = descriptorMapFromList(descriptors)
    script.value = normalizeScriptRecord(record, descriptorMap, [])
    if (script.value.available === false) {
      throw new Error(script.value.unavailableReason || `脚本类型 ${script.value.type} 当前未启用`)
    }
    formModel.value = preservedFormModel ?? cloneValue(record.config || {})
    loadError.value = null
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    if (showError) {
      loadError.value = errorMsg
    }
    logger.error(`加载插件脚本失败: ${errorMsg}`)
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
    await loadScript({
      preserveFormModel: true,
      redirectOnError: false,
      showError: false,
    })
  } finally {
    schemaRefreshInFlight.value = false
  }
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
    await loadScript()
  },
  onActionSuccess: ({ response }) => {
    const formPatch = response?.data?.formPatch || response?.formPatch
    if (!isPlainObject(formPatch)) {
      return false
    }
    formModel.value = mergeFormPatch(formModel.value, formPatch)
    return true
  },
})

const handleFieldAction = async (field: string, fieldSchema: SchemaFieldDefinition) => {
  await runFieldAction(field, fieldSchema, {
    scriptId,
    scriptName: script.value?.name || '',
    scriptType: script.value?.type || '',
    scriptDisplayName: script.value?.displayName || '',
    supportedModes: script.value?.supportedModes || [],
    docsUrl: script.value?.docsUrl || null,
    formModel: formModel.value,
  })
}

const handleSave = async () => {
  const result = schemaFormRef.value?.validate()
  if (result && !result.valid) {
    message.error('请先修正表单校验错误')
    return
  }

  saving.value = true
  try {
    await api.updateScript(scriptId, formModel.value)
    message.success('脚本配置已保存')
    await loadScript()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存插件脚本失败: ${errorMsg}`)
    message.error(errorMsg)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  pluginSystemSubscriptionId = subscribe({ id: 'PluginSystem' }, handlePluginSystemMessage)
  void loadScript()
})

onUnmounted(() => {
  if (pluginSystemSubscriptionId) {
    unsubscribe(pluginSystemSubscriptionId)
    pluginSystemSubscriptionId = null
  }
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  gap: 16px;
}

.header-nav {
  min-width: 0;
}

.config-card {
  border-radius: 16px;
}

.config-load-error {
  margin-bottom: 16px;
}

.script-icon {
  width: 24px;
  height: 24px;
  object-fit: contain;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
