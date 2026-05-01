<template>
  <div class="page-header">
    <div class="header-nav">
      <a-breadcrumb>
        <a-breadcrumb-item>
          <router-link to="/scripts">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit/schema`">{{ scriptName }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>{{ isEdit ? '编辑用户' : '创建用户' }}</a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button type="primary" :loading="saving" @click="handleSave">保存配置</a-button>
      <a-button @click="router.push('/scripts')">返回</a-button>
    </a-space>
  </div>

  <a-card class="config-card" :loading="loading">
    <template #title>
      <a-space>
        <span>{{ userName || '用户配置' }}</span>
        <a-tag :color="getScriptTypeTagColor(scriptType)">{{ scriptDisplayName }}</a-tag>
      </a-space>
    </template>

    <SchemaForm
      v-if="userSchema"
      ref="schemaFormRef"
      v-model="formModel"
      :schema="userSchema"
      @validation-change="(errors) => (fieldErrors = errors)"
    />
  </a-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import SchemaForm from '@/components/SchemaForm.vue'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import type { SchemaDefinition, SchemaValidationErrorMap } from '@/types/schemaForm'
import { descriptorMapFromList } from '@/utils/scriptRegistry'
import { getScriptTypeTagColor } from '@/utils/scriptRegistry'

const logger = window.electronAPI.getLogger('通用用户编辑')

const route = useRoute()
const router = useRouter()
const api = useScriptRegistryApi()

const loading = ref(true)
const saving = ref(false)
const fieldErrors = ref<SchemaValidationErrorMap>({})
const schemaFormRef = ref<InstanceType<typeof SchemaForm> | null>(null)

const scriptId = route.params.scriptId as string
const routeUserId = route.params.userId as string | undefined
const isEdit = ref(Boolean(routeUserId))
const userId = ref(routeUserId || '')
const scriptName = ref('')
const userName = ref('')
const scriptType = ref('')
const scriptDisplayName = ref('')
const userSchema = ref<SchemaDefinition | null>(null)
const formModel = ref<Record<string, any>>({})

const displayNameFromForm = computed(() => {
  const info = formModel.value?.Info
  return typeof info?.Name === 'string' && info.Name.trim() ? info.Name : ''
})

const loadData = async () => {
  loading.value = true
  try {
    const [descriptors, scripts] = await Promise.all([api.getScriptTypes(), api.getScripts(scriptId)])
    const scriptRecord = scripts[0]
    if (!scriptRecord) {
      throw new Error('脚本不存在')
    }

    const descriptorMap = descriptorMapFromList(descriptors)
    const descriptor = descriptorMap[scriptRecord.type]
    scriptName.value = scriptRecord.name
    scriptType.value = scriptRecord.type
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

  saving.value = true
  try {
    await api.updateUser(scriptId, userId.value, formModel.value)
    userName.value = displayNameFromForm.value || userName.value
    message.success('用户配置已保存')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存通用用户失败: ${errorMsg}`)
    message.error(errorMsg)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadData()
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

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
