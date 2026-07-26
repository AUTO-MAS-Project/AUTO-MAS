<template>
  <ScriptEditPageHeader
    :title="script?.name || '脚本配置'"
    subtitle="按脚本 Schema 编辑配置，敏感字段保存后自动脱敏"
    :type-label="script?.displayName || script?.type || '未知类型'"
    :type-color="getScriptTypeTagColor(script?.type || '', script?.themeColor)"
    @back="router.push('/scripts')"
  >
    <template #actions>
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
    </template>
  </ScriptEditPageHeader>

  <a-card class="config-card" :loading="loading">
    <a-alert
      v-if="loadError"
      class="config-load-error"
      type="error"
      show-icon
      message="脚本配置加载失败"
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
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import HeaderSchemaActionButton from '@/components/HeaderSchemaActionButton.vue'
import SchemaForm from '@/components/SchemaForm.vue'
import SchemaActionSessionMask from '@/components/SchemaActionSessionMask.vue'
import { useSchemaActionRunner } from '@/composables/useSchemaActionRunner'
import {
  buildSchemaSavePayload,
  sanitizeErrorForLog,
} from '@/composables/useSensitiveFieldStrategy'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import type { Script } from '@/types/script'
import type { SchemaFieldDefinition, SchemaValidationErrorMap } from '@/types/schemaForm'
import {
  descriptorMapFromList,
  getScriptTypeTagColor,
  normalizeScriptRecord,
} from '@/utils/scriptRegistry'
import { collectHeaderSchemaActions } from '@/utils/schemaActions'
import ScriptEditPageHeader from './ScriptEditPageHeader.vue'

const logger = window.electronAPI.getLogger('通用脚本编辑')

const route = useRoute()
const router = useRouter()
const api = useScriptRegistryApi()

const loading = ref(true)
const saving = ref(false)
const loadError = ref<string | null>(null)
const script = ref<Script | null>(null)
const formModel = ref<Record<string, any>>({})
const fieldErrors = ref<SchemaValidationErrorMap>({})
const schemaFormRef = ref<InstanceType<typeof SchemaForm> | null>(null)
const headerSchemaActions = computed(() => collectHeaderSchemaActions(script.value?.schema || null))
const headerSchemaActionKeys = computed(() => headerSchemaActions.value.map(action => action.key))

const scriptId = route.params.id as string

const loadScript = async () => {
  loading.value = true
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
    formModel.value = JSON.parse(JSON.stringify(record.config || {}))
    loadError.value = null
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    loadError.value = errorMsg
    logger.error(`加载通用脚本失败: ${errorMsg}`)
    message.error(errorMsg)
  } finally {
    loading.value = false
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
})

const handleFieldAction = async (field: string, fieldSchema: SchemaFieldDefinition) => {
  await runFieldAction(field, fieldSchema, {
    scriptId,
    scriptName: script.value?.name || '',
    scriptType: script.value?.type || '',
    scriptDisplayName: script.value?.displayName || '',
    supportedModes: script.value?.supportedModes || [],
    formModel: formModel.value,
  })
}

const handleSave = async () => {
  const result = schemaFormRef.value?.validate()
  if (result && !result.valid) {
    message.error('请先修正表单校验错误')
    return
  }

  const schema = script.value?.schema || {}
  const payload =
    schemaFormRef.value?.buildSavePayload() ?? buildSchemaSavePayload(formModel.value, schema, {})
  saving.value = true
  try {
    await api.updateScript(scriptId, payload)
    schemaFormRef.value?.resetSensitiveDrafts()
    message.success('脚本配置已保存')
    await loadScript()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    const safeError = sanitizeErrorForLog(
      sanitizeErrorForLog(errorMsg, payload, schema),
      formModel.value,
      schema
    )
    logger.error(`保存通用脚本失败: ${safeError}`)
    message.error(safeError)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadScript()
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--v6-space-6);
  gap: var(--v6-space-4);
}

.header-nav {
  min-width: 0;
}

.config-card {
  border-radius: var(--v6-radius-lg);
  background: var(--v6-color-surface);
  border: 1px solid var(--v6-color-border-subtle);
  box-shadow: var(--v6-shadow-card);
}

.config-load-error {
  margin-bottom: var(--v6-space-4);
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
<style scoped src="./script-edit-surface.css"></style>
