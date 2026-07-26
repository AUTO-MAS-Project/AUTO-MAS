<template>
  <div class="user-edit-page">
    <PageHeader
      :title="userName || (isEdit ? '编辑用户' : '创建用户')"
      :subtitle="scriptName ? `${scriptName} · 用户运行配置` : '用户运行配置'"
      :bordered="false"
      compact
      transparent
    >
      <a-tag :color="getScriptTypeTagColor(scriptType, scriptThemeColor)">
        {{ scriptDisplayName || '通用脚本' }}
      </a-tag>
      <template #actions>
        <HeaderSchemaActionButton
          v-for="action in headerSchemaActions"
          :key="action.key"
          :action="action"
          :loading="actionLoadingId === action.key"
          @click="handleFieldAction(action.key, action.field)"
        />
        <a-button type="primary" :loading="saving" @click="handleSave">保存配置</a-button>
        <a-button @click="router.push('/scripts')">返回</a-button>
      </template>
    </PageHeader>

    <main class="user-edit-content">
      <a-spin :spinning="loading" tip="加载用户配置中...">
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
          <a-empty v-else-if="!loading" description="此脚本类型未提供用户配置表单" />
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
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import HeaderSchemaActionButton from '@/components/HeaderSchemaActionButton.vue'
import PageHeader from '@/components/mac/PageHeader.vue'
import SchemaForm from '@/components/SchemaForm.vue'
import SchemaActionSessionMask from '@/components/SchemaActionSessionMask.vue'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useSchemaActionRunner } from '@/composables/useSchemaActionRunner'
import {
  buildSchemaSavePayload,
  sanitizeErrorForLog,
} from '@/composables/useSensitiveFieldStrategy'
import type {
  SchemaDefinition,
  SchemaFieldDefinition,
  SchemaValidationErrorMap,
} from '@/types/schemaForm'
import { descriptorMapFromList } from '@/utils/scriptRegistry'
import { getScriptTypeTagColor } from '@/utils/scriptRegistry'
import { collectHeaderSchemaActions } from '@/utils/schemaActions'

const logger = window.electronAPI.getLogger('通用用户编辑')

const route = useRoute()
const router = useRouter()
const api = useScriptRegistryApi()

const loading = ref(true)
const saving = ref(false)
const saveError = ref('')
const fieldErrors = ref<SchemaValidationErrorMap>({})
const schemaFormRef = ref<InstanceType<typeof SchemaForm> | null>(null)

const scriptId = route.params.scriptId as string
const routeUserId = route.params.userId as string | undefined
const isEdit = ref(Boolean(routeUserId))
const userId = ref(routeUserId || '')
const scriptName = ref('')
const userName = ref('')
const scriptType = ref('')
const scriptThemeColor = ref<string | null>(null)
const scriptDisplayName = ref('')
const userSchema = ref<SchemaDefinition | null>(null)
const formModel = ref<Record<string, any>>({})
const headerSchemaActions = computed(() => collectHeaderSchemaActions(userSchema.value))
const headerSchemaActionKeys = computed(() => headerSchemaActions.value.map(action => action.key))

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

const loadData = async () => {
  loading.value = true
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
    const descriptor = descriptorMap[scriptRecord.type]
    scriptName.value = scriptRecord.name
    scriptType.value = scriptRecord.type
    scriptThemeColor.value = scriptRecord.theme_color || descriptor?.theme_color || null
    scriptDisplayName.value = descriptor?.display_name || scriptRecord.type
    userSchema.value = descriptor?.user_schema || null

    if (!userId.value) {
      const created = await api.addUser(scriptId)
      userId.value = created.id
      isEdit.value = true
      router.replace(`/scripts/${scriptId}/users/${created.id}/edit/schema`)
    }

    const users = await api.getUsers(scriptId, userId.value)
    const user = users[0]
    if (!user) {
      throw new Error('用户不存在')
    }

    userName.value = user.name
    userSchema.value = user.schema || descriptor?.user_schema || null
    formModel.value = JSON.parse(JSON.stringify(user.config || {}))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载通用用户失败: ${errorMsg}`)
    message.error(errorMsg)
    router.push('/scripts')
  } finally {
    loading.value = false
  }
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
      throw new Error('用户配置保存失败')
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
    logger.error(`保存通用用户失败: ${safeError}`)
    saveError.value = safeError
    message.error(safeError)
  } finally {
    saving.value = false
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
})

const handleFieldAction = async (field: string, fieldSchema: SchemaFieldDefinition) => {
  await runFieldAction(field, fieldSchema, {
    scriptId,
    scriptName: scriptName.value,
    scriptType: scriptType.value,
    scriptDisplayName: scriptDisplayName.value,
    userId: userId.value,
    userName: displayNameFromForm.value || userName.value,
    formModel: formModel.value,
  })
}

onMounted(() => {
  void loadData()
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
