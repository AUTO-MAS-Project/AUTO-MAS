<template>
  <div class="page-header">
    <div class="header-nav">
      <a-breadcrumb>
        <a-breadcrumb-item>
          <router-link to="/scripts">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>通用脚本编辑</a-breadcrumb-item>
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
        <span>{{ script?.name || '脚本配置' }}</span>
        <a-tag :color="getScriptTypeTagColor(script?.type || '', script?.themeColor)">
          {{ script?.displayName || script?.type || '未知类型' }}
        </a-tag>
      </a-space>
    </template>

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
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import type { Script } from '@/types/script'
import type { SchemaFieldDefinition, SchemaValidationErrorMap } from '@/types/schemaForm'
import {
  descriptorMapFromList,
  getScriptTypeTagColor,
  normalizeScriptRecord,
} from '@/utils/scriptRegistry'
import { collectHeaderSchemaActions } from '@/utils/schemaActions'

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

  saving.value = true
  try {
    await api.updateScript(scriptId, formModel.value)
    message.success('脚本配置已保存')
    await loadScript()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存通用脚本失败: ${errorMsg}`)
    message.error(errorMsg)
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

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
