<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ApiOutlined, DeleteOutlined, EditOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { useWebhookApi } from '@/composables/useWebhookApi'
import { useApiQuery } from '@/composables/useApiQuery'
import { apiErrorMessage } from '@/utils/apiResult'
import ApiRetryAlert from './ApiRetryAlert.vue'
import type { Webhook_Input } from '@/api/models/Webhook_Input'
import type { app__models__config__setting__Webhook__Data } from '@/api/models/app__models__config__setting__Webhook__Data'
import SettingToggleButton from './SettingToggleButton.vue'
import { TEMPLATE_VARIABLES, WEBHOOK_TEMPLATES } from '@/utils/webhookTemplates'

interface CustomWebhook { id: string; name: string; url: string; template: string; enabled: boolean; headers?: Record<string, string>; method?: 'POST' | 'GET' }
interface WebhookItem extends CustomWebhook { uid: string; method: 'POST' | 'GET' }

const props = withDefaults(defineProps<{
  webhooks?: CustomWebhook[]
  scriptId?: string | null
  userId?: string | null
  mode?: 'global' | 'user'
  compact?: boolean
  getPopupContainer?: () => HTMLElement
}>(), { webhooks: undefined, scriptId: null, userId: null, mode: undefined, compact: false, getPopupContainer: undefined })

const emit = defineEmits<{ 'update:webhooks': [webhooks: CustomWebhook[]]; change: []; listed: [webhooks: WebhookItem[]] }>()
const { t } = useI18n()
const logger = window.electronAPI.getLogger('Webhook')
const modalVisible = ref(false)
const isEditing = ref(false)
const submitting = ref(false)
const api = useWebhookApi()
const toggling = ref<Record<string, boolean>>({})
const selectedTemplate = ref<string>()
const testing = ref<Record<string, boolean>>({})
const apiWebhooks = ref<WebhookItem[]>([])
const formData = reactive({ uid: '', name: '', url: '', template: '', method: 'POST' as 'POST' | 'GET', enabled: true, headersList: [] as Array<{ key: string; value: string }> })
const localWebhooks = computed({ get: () => props.webhooks ?? [], set: value => emit('update:webhooks', value) })
const displayWebhooks = computed(() => props.mode === 'global' ? apiWebhooks.value : localWebhooks.value.map(item => ({ ...item, uid: item.id, method: item.method ?? 'POST' })))

const toPayload = () => ({ info: { name: formData.name, enabled: formData.enabled }, data: { url: formData.url, template: formData.template, method: formData.method, headers: JSON.stringify(Object.fromEntries(formData.headersList.filter(item => item.key).map(item => [item.key, item.value]))) } })
const mapApiWebhook = (uid: string, raw: Record<string, unknown>): WebhookItem => {
  const info = (raw.info ?? raw.Info ?? {}) as Record<string, unknown>
  const data = (raw.data ?? raw.Data ?? {}) as Record<string, unknown>
  let headers: Record<string, string> | undefined
  try { headers = data.headers ? JSON.parse(String(data.headers)) : undefined } catch { headers = undefined }
  return { uid, id: uid, name: String(info.name ?? info.Name ?? ''), url: String(data.url ?? data.Url ?? ''), template: String(data.template ?? data.Template ?? ''), method: (data.method ?? data.Method ?? 'POST') as 'POST' | 'GET', enabled: Boolean(info.enabled ?? info.Enabled), headers }
}

const { loading, error: loadError, execute: loadWebhooks } = useApiQuery(async () => {
  if (props.mode !== 'global') return
  const response = await api.getWebhooks()
  const order = response.order ?? []
  const data = response.data ?? {}
  apiWebhooks.value = order.map(item => mapApiWebhook(item.uid, (data[item.uid] ?? {}) as Record<string, unknown>))
  emit('listed', apiWebhooks.value)
}, () => t('comp.couldNotLoadWebhook'))

const resetForm = () => { Object.assign(formData, { uid: '', name: '', url: '', template: '', method: 'POST', enabled: true, headersList: [] }); selectedTemplate.value = undefined }
const showAddModal = () => { resetForm(); isEditing.value = false; modalVisible.value = true }
const editWebhook = (item: WebhookItem) => { Object.assign(formData, { uid: item.uid, name: item.name, url: item.url, template: item.template, method: item.method, enabled: item.enabled, headersList: Object.entries(item.headers ?? {}).map(([key, value]) => ({ key, value })) }); isEditing.value = true; modalVisible.value = true }
const applyTemplate = (name?: string) => { const template = WEBHOOK_TEMPLATES.find(item => item.name === name); if (template) { formData.name = ''; formData.url = template.example ?? ''; formData.template = template.template ?? '' } }
const addHeader = () => formData.headersList.push({ key: '', value: '' })
const removeHeader = (index: number) => formData.headersList.splice(index, 1)
const toggle = async (item: WebhookItem, enabled: boolean) => {
  if (toggling.value[item.uid]) return
  toggling.value[item.uid] = true
  try {
    await api.updateWebhook({ webhookId: item.uid, data: { info: { enabled } } })
    item.enabled = enabled
  } catch (error) {
    message.error(apiErrorMessage(error, t('comp.couldNotSaveWebhook')))
  } finally {
    toggling.value[item.uid] = false
  }
}
const asPayload = (item: Pick<WebhookItem, 'name' | 'enabled' | 'url' | 'template' | 'method' | 'headers'>): Webhook_Input => ({ info: { name: item.name, enabled: item.enabled }, data: { url: item.url, template: item.template, method: item.method as app__models__config__setting__Webhook__Data.method, headers: JSON.stringify(item.headers ?? {}) } })
const deleteWebhook = (item: WebhookItem) => Modal.confirm({
  title: t('comp.confirmDeletion'),
  okType: 'danger',
  onOk: async () => {
    try {
      if (props.mode === 'global') {
        await api.deleteWebhook(item.uid)
        await loadWebhooks()
      } else {
        localWebhooks.value = localWebhooks.value.filter(value => value.id !== item.uid)
        emit('change')
      }
    } catch (error) {
      message.error(apiErrorMessage(error, t('comp.couldNotSaveWebhook')))
      throw error
    }
  },
})
const testWebhook = async (item: WebhookItem) => {
  if (testing.value[item.uid]) return
  testing.value[item.uid] = true
  try {
    if (props.mode !== 'global') { message.info(t('comp.test')); return }
    await api.testWebhook({ data: asPayload(item) })
    message.success(t('comp.webhookP0TestedSuccessfully', { p0: item.name }))
  } catch (error) {
    message.error(apiErrorMessage(error, t('comp.webhookTestFailedP0')))
  } finally {
    testing.value[item.uid] = false
  }
}
const submit = async () => { submitting.value = true; try { if (props.mode !== 'global') { const value: CustomWebhook = { id: formData.uid || `webhook_${Date.now()}`, name: formData.name, url: formData.url, template: formData.template, method: formData.method, enabled: formData.enabled, headers: Object.fromEntries(formData.headersList.filter(item => item.key).map(item => [item.key, item.value])) }; localWebhooks.value = isEditing.value ? localWebhooks.value.map(item => item.id === value.id ? value : item) : [...localWebhooks.value, value]; emit('change'); modalVisible.value = false; return } if (!formData.uid) { const created = await api.addWebhook(); formData.uid = created.webhookId ?? '' } await api.updateWebhook({ webhookId: formData.uid, data: toPayload() as Webhook_Input }); modalVisible.value = false; await loadWebhooks(); message.success(t(isEditing.value ? 'comp.webhookUpdated' : 'comp.webhookAdded')) } catch (error) { logger.error(String(error)); message.error(apiErrorMessage(error, t('comp.couldNotSaveWebhook'))) } finally { submitting.value = false } }
const saveLocalToggle = (item: WebhookItem, enabled: boolean) => { localWebhooks.value = localWebhooks.value.map(value => value.id === item.uid ? { ...value, enabled } : value); emit('change') }
onMounted(() => void loadWebhooks())
watch(() => [props.mode, props.scriptId, props.userId], () => void loadWebhooks())
</script>

<template>
  <div class="webhook-manager" :class="{ compact }">
    <div v-if="!compact" class="webhook-header"><h3>{{ t('comp.customWebhooks') }}</h3><a-button type="primary" @click="showAddModal"><PlusOutlined />{{ t('comp.addWebhook') }}</a-button></div>
    <ApiRetryAlert :error="loadError" :loading="loading" @retry="loadWebhooks" />
    <a-spin v-if="loading && !displayWebhooks.length" class="webhook-loading" />
    <div v-else-if="displayWebhooks.length" class="webhook-list">
      <div v-for="item in displayWebhooks" :key="item.uid" class="webhook-item">
        <div class="webhook-info"><div class="webhook-name"><span>{{ item.name }}</span><a-tag :color="item.enabled ? 'green' : 'red'">{{ item.enabled ? t('common.on') : t('common.off') }}</a-tag></div><div class="webhook-url">{{ item.url }}</div></div>
        <div class="webhook-actions">
          <SettingToggleButton :model-value="item.enabled" :disabled="toggling[item.uid]" :loading="toggling[item.uid]" @change="next => props.mode === 'global' ? toggle(item, next) : saveLocalToggle(item, next)" />
          <a-button type="text" :loading="testing[item.uid]" @click="testWebhook(item)"><PlayCircleOutlined />{{ t('comp.test') }}</a-button>
          <a-button type="text" @click="editWebhook(item)"><EditOutlined />{{ t('comp.edit') }}</a-button>
          <a-button type="text" danger @click="deleteWebhook(item)"><DeleteOutlined />{{ t('comp.delete') }}</a-button>
        </div>
      </div>
    </div>
    <a-empty v-else-if="!loadError" :description="t('comp.noCustomWebhooks')"><template #image><ApiOutlined /></template></a-empty>
    <a-button v-if="compact" type="dashed" class="add-hook" @click="showAddModal"><PlusOutlined />{{ t('comp.addWebhook') }}</a-button>
    <a-modal v-model:open="modalVisible" :title="isEditing ? t('comp.editWebhook') : t('comp.addWebhook')" :confirm-loading="submitting" @ok="submit">
      <a-form layout="vertical">
        <a-form-item :label="t('comp.pickTemplate')"><a-select v-model:value="selectedTemplate" allow-clear @change="applyTemplate"><a-select-option v-for="item in WEBHOOK_TEMPLATES" :key="item.name" :value="item.name">{{ item.name }}</a-select-option></a-select></a-form-item>
        <a-row :gutter="16"><a-col :span="12"><a-form-item :label="t('comp.webhookName')"><a-input v-model:value="formData.name" /></a-form-item></a-col><a-col :span="12"><a-form-item :label="t('comp.method')"><a-select v-model:value="formData.method"><a-select-option value="POST">POST</a-select-option><a-select-option value="GET">GET</a-select-option></a-select></a-form-item></a-col></a-row>
        <a-form-item label="Webhook URL"><a-input v-model:value="formData.url" /></a-form-item>
        <a-form-item :label="t('comp.messageTemplate')"><a-textarea v-model:value="formData.template" :rows="5" /><div><a-tag v-for="item in TEMPLATE_VARIABLES" :key="item.name" size="small">{{ item.name }}</a-tag></div></a-form-item>
        <a-form-item :label="t('comp.customHeadersOptional')"><div v-for="(item, index) in formData.headersList" :key="index"><a-input v-model:value="item.key" /><a-input v-model:value="item.value" /><a-button type="text" danger @click="removeHeader(index)"><DeleteOutlined /></a-button></div><a-button type="dashed" block @click="addHeader"><PlusOutlined />{{ t('comp.addHeader') }}</a-button></a-form-item>
        <a-form-item><SettingToggleButton v-model="formData.enabled" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.webhook-loading { display: flex; min-height: 160px; align-items: center; justify-content: center; }
.webhook-header,.webhook-item,.webhook-name,.webhook-actions { display:flex; align-items:center; gap:12px; }
.webhook-header { justify-content:space-between; margin-bottom:12px; }
.webhook-header h3 { margin:0; }
.webhook-item { justify-content:space-between; padding:12px 0; border-bottom:1px solid var(--ant-color-border-secondary); }
.webhook-info { min-width:0; flex:1; }.webhook-name { font-weight:600; }.webhook-url { color:var(--ant-color-text-secondary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.webhook-actions { flex-wrap:wrap; justify-content:flex-end; }.add-hook { width:100%; margin-top:12px; }
</style>
