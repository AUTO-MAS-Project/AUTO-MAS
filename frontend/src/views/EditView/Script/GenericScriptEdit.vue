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
      <a-button type="primary" :loading="saving" @click="handleSave">保存配置</a-button>
      <a-button v-if="script?.docsUrl" :href="script.docsUrl || undefined" target="_blank">
        查看文档
      </a-button>
      <a-button @click="router.push('/scripts')">返回</a-button>
    </a-space>
  </div>

  <a-card class="config-card" :loading="loading">
    <template #title>
      <a-space>
        <span>{{ script?.name || '脚本配置' }}</span>
        <a-tag :color="getScriptTypeTagColor(script?.type || '')">
          {{ script?.displayName || script?.type || '未知类型' }}
        </a-tag>
      </a-space>
    </template>

    <SchemaForm
      v-if="script"
      ref="schemaFormRef"
      v-model="formModel"
      :schema="script.schema || {}"
      @validation-change="(errors) => (fieldErrors = errors)"
    />
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import SchemaForm from '@/components/SchemaForm.vue'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import type { Script } from '@/types/script'
import type { SchemaValidationErrorMap } from '@/types/schemaForm'
import { descriptorMapFromList, getScriptTypeTagColor, normalizeScriptRecord } from '@/utils/scriptRegistry'

const logger = window.electronAPI.getLogger('通用脚本编辑')

const route = useRoute()
const router = useRouter()
const api = useScriptRegistryApi()

const loading = ref(true)
const saving = ref(false)
const script = ref<Script | null>(null)
const formModel = ref<Record<string, any>>({})
const fieldErrors = ref<SchemaValidationErrorMap>({})
const schemaFormRef = ref<InstanceType<typeof SchemaForm> | null>(null)

const scriptId = route.params.id as string

const loadScript = async () => {
  loading.value = true
  try {
    const [descriptors, records] = await Promise.all([api.getScriptTypes(), api.getScripts(scriptId)])
    const record = records[0]
    if (!record) {
      throw new Error('脚本不存在')
    }

    const descriptorMap = descriptorMapFromList(descriptors)
    script.value = normalizeScriptRecord(record, descriptorMap, [])
    formModel.value = JSON.parse(JSON.stringify(record.config || {}))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载通用脚本失败: ${errorMsg}`)
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

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
