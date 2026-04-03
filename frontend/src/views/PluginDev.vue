<template>
  <div class="plugin-dev-page">
    <div class="scripts-header">
      <div class="header-left">
        <h1 class="page-title">插件管理</h1>
      </div>
      <div class="header-actions">
        <a-space>
          <a-button :loading="loading" @click="fetchData">刷新</a-button>
          <a-button type="primary" @click="openAddModal">新增实例</a-button>
          <a-button :loading="reloadingAll" @click="reloadAll">重载全部</a-button>
        </a-space>
      </div>
    </div>

    <a-row :gutter="12" class="main-layout">
      <a-col :span="7">
        <div class="left-panel">
          <a-card :bordered="false" title="插件实例列表" class="section-card list-card">
            <template #extra>
              <a-tag>v{{ version }}</a-tag>
            </template>

            <a-input v-model:value="keyword" placeholder="搜索实例ID/名称/插件" allow-clear class="search-box" />

            <div class="instance-list">
              <a-empty v-if="filteredInstances.length === 0" description="暂无实例" />
              <div
                v-for="item in filteredInstances"
                :key="item.id"
                class="instance-item"
                :class="{ active: selectedInstanceId === item.id }"
                @click="selectInstance(item.id)"
              >
                <div class="instance-item-header">
                  <span class="instance-name">{{ item.name || item.id }}</span>
                  <a-switch
                    :checked="item.enabled"
                    checked-children="启用"
                    un-checked-children="禁用"
                    @click.stop
                    @update:checked="(val: boolean) => toggleInstanceEnabled(item, val)"
                  />
                </div>
                <div class="instance-plugin">{{ item.plugin }}</div>
                <div class="instance-id">{{ item.id }}</div>
                <div class="instance-runtime" v-if="getRuntimeState(item.id)">
                  <a-space size="6" wrap>
                    <a-tag :color="getStatusTagColor(getRuntimeState(item.id)?.status)">
                      {{ getRuntimeState(item.id)?.status || 'unknown' }}
                    </a-tag>
                    <a-tag :color="getPhaseTagColor(getRuntimeState(item.id)?.lifecycle_phase)">
                      {{ getRuntimeState(item.id)?.lifecycle_phase || 'idle' }}
                    </a-tag>
                    <a-tag color="blue">g{{ getRuntimeState(item.id)?.generation ?? 0 }}</a-tag>
                    <a-tag color="purple">reload {{ getRuntimeState(item.id)?.reload_count ?? 0 }}</a-tag>
                  </a-space>
                </div>
              </div>
            </div>
          </a-card>
        </div>
      </a-col>

      <a-col :span="17">
        <a-card :bordered="false" class="section-card detail-card">
          <template #title>
            <div class="detail-title">
              <span>{{ selectedInstance ? selectedInstance.plugin : '实例配置' }}</span>
            </div>
          </template>
          <template #extra>
            <a-space v-if="selectedInstance" wrap>
              <a-button type="primary" :loading="submitting" @click="submitEdit">
                保存配置
              </a-button>
              <a-button :disabled="!isDirty" @click="resetEdit">重置改动</a-button>
              <a-button @click="openJsonPreview">查看当前 JSON</a-button>
              <a-button @click="reloadInstance(editForm.instanceId)">重载实例</a-button>
              <a-button @click="reloadPlugin(editForm.plugin)">重载同插件</a-button>
              <a-popconfirm title="确认删除该实例？" @confirm="deleteInstance(editForm.instanceId)">
                <a-button danger>删除实例</a-button>
              </a-popconfirm>
            </a-space>
          </template>

          <div class="detail-scroll" @wheel.stop>
            <template v-if="selectedInstance">
            <a-alert
              v-if="isDirty"
              type="warning"
              show-icon
              message="当前有未保存改动"
              style="margin-bottom: 12px"
            />

            <a-alert
              v-if="currentSchemaError"
              type="error"
              show-icon
              :message="`Schema 加载失败：${currentSchemaError}`"
              style="margin-bottom: 12px"
            />

            <a-alert
              v-if="!currentSchemaError && activeSchemaEntries.length === 0"
              type="warning"
              show-icon
              message="该插件未声明 schema，可能非预期行为或插件本身无需配置"
              style="margin-bottom: 12px"
            />

            <a-card v-if="selectedRuntimeState" size="small" class="runtime-observer-card" title="运行态观测">
              <a-descriptions :column="2" size="small" bordered>
                <a-descriptions-item label="运行状态">
                  <a-tag :color="getStatusTagColor(selectedRuntimeState.status)">
                    {{ selectedRuntimeState.status }}
                  </a-tag>
                </a-descriptions-item>
                <a-descriptions-item label="生命周期阶段">
                  <a-tag :color="getPhaseTagColor(selectedRuntimeState.lifecycle_phase)">
                    {{ selectedRuntimeState.lifecycle_phase }}
                  </a-tag>
                </a-descriptions-item>
                <a-descriptions-item label="代际">g{{ selectedRuntimeState.generation }}</a-descriptions-item>
                <a-descriptions-item label="重载次数">{{ selectedRuntimeState.reload_count }}</a-descriptions-item>
                <a-descriptions-item label="最近重载原因">
                  {{ selectedRuntimeState.last_reload_reason || '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="最近重载时间">
                  {{ formatRuntimeTime(selectedRuntimeState.last_reload_at) }}
                </a-descriptions-item>
                <a-descriptions-item label="阶段更新时间">
                  {{ formatRuntimeTime(selectedRuntimeState.lifecycle_updated_at) }}
                </a-descriptions-item>
                <a-descriptions-item label="最近错误">
                  {{ selectedRuntimeState.last_error || '-' }}
                </a-descriptions-item>
              </a-descriptions>
            </a-card>

            <a-form layout="vertical">
              <a-form-item label="实例名称">
                <a-input v-model:value="editForm.name" placeholder="输入实例名称" />
              </a-form-item>

              <a-card size="small" title="Schema 动态表单" class="editor-card">
                <template v-if="activeSchemaEntries.length > 0">
                  <a-form-item
                    v-for="([field, fieldSchema], index) in activeSchemaEntries"
                    :key="field"
                    :label="fieldSchema.description || field"
                    :required="Boolean(fieldSchema.required)"
                    :class="['schema-item', `schema-item-${fieldSchema.type}`]"
                    :style="{ marginBottom: index === activeSchemaEntries.length - 1 ? '0' : '16px' }"
                  >
                    <div class="schema-field-head">
                      <a-space size="6">
                        <a-tag class="type-tag" color="processing">{{ getTypeLabel(fieldSchema) }}</a-tag>
                        <a-tag v-if="fieldSchema.required" color="error">必填</a-tag>
                        <a-tag v-if="isPasswordSchema(fieldSchema)" color="gold">敏感</a-tag>
                      </a-space>
                    </div>

                    <template v-if="fieldSchema.type === 'boolean'">
                      <a-switch
                        :checked="getBooleanValue(field)"
                        checked-children="是"
                        un-checked-children="否"
                        @update:checked="(val: boolean) => updateFieldValue(field, val)"
                      />
                    </template>

                    <template v-else-if="fieldSchema.type === 'string'">
                      <a-input-password
                        v-if="isPasswordSchema(fieldSchema)"
                        :value="String(getFieldValue(field) ?? '')"
                        @update:value="(val: string) => updateFieldValue(field, val)"
                      />
                      <a-input
                        v-else
                        :value="String(getFieldValue(field) ?? '')"
                        @update:value="(val: string) => updateFieldValue(field, val)"
                      />
                    </template>

                    <template v-else-if="fieldSchema.type === 'number'">
                      <a-input-number
                        :value="getNumberValue(field)"
                        style="width: 100%"
                        :step="1"
                        @update:value="(val: number | null) => updateFieldValue(field, val)"
                      />
                    </template>

                    <template v-else-if="fieldSchema.type === 'list'">
                      <a-space direction="vertical" style="width: 100%">
                        <a-button size="small" @click="addListRow(field, fieldSchema.item_type)">新增一行</a-button>
                        <a-table
                          :columns="listColumns"
                          :data-source="getListRows(field)"
                          :pagination="false"
                          size="small"
                          row-key="__rowKey"
                        >
                          <template #bodyCell="{ column, record, index }">
                            <template v-if="column.key === 'value'">
                              <a-switch
                                v-if="fieldSchema.item_type === 'boolean'"
                                :checked="Boolean(record.value)"
                                @update:checked="(val: boolean) => updateListRowValue(field, index, val, fieldSchema.item_type)"
                              />
                              <a-input-number
                                v-else-if="fieldSchema.item_type === 'number'"
                                style="width: 100%"
                                :value="typeof record.value === 'number' ? record.value : Number(record.value || 0)"
                                @update:value="(val: number | null) => updateListRowValue(field, index, val ?? 0, fieldSchema.item_type)"
                              />
                              <a-input
                                v-else
                                :value="String(record.value ?? '')"
                                @update:value="(val: string) => updateListRowValue(field, index, val, fieldSchema.item_type)"
                              />
                            </template>
                            <template v-else-if="column.key === 'action'">
                              <a-button danger size="small" @click="removeListRow(field, index)">删除</a-button>
                            </template>
                          </template>
                        </a-table>
                      </a-space>
                    </template>

                    <template v-else-if="fieldSchema.type === 'key_value'">
                      <a-space direction="vertical" style="width: 100%">
                        <a-button size="small" @click="addKeyValueRow(field)">新增一行</a-button>
                        <a-table
                          :columns="keyValueColumns"
                          :data-source="getKeyValueRows(field)"
                          :pagination="false"
                          size="small"
                          row-key="__rowKey"
                        >
                          <template #bodyCell="{ column, record }">
                            <template v-if="column.key === 'key'">
                              <a-input
                                :value="record.key"
                                @blur="(e: FocusEvent) => updateKeyValueRowKey(field, record.key, String((e.target as HTMLInputElement).value || ''))"
                              />
                            </template>
                            <template v-else-if="column.key === 'value'">
                              <a-input
                                :value="record.value"
                                @update:value="(val: string) => updateKeyValueRowValue(field, record.key, val)"
                              />
                            </template>
                            <template v-else-if="column.key === 'action'">
                              <a-button danger size="small" @click="removeKeyValueRow(field, record.key)">删除</a-button>
                            </template>
                          </template>
                        </a-table>
                      </a-space>
                    </template>

                    <template v-else-if="fieldSchema.type === 'table'">
                      <a-space direction="vertical" style="width: 100%">
                        <a-space>
                          <a-button size="small" @click="addTableRow(field)">新增行</a-button>
                          <a-button size="small" @click="addTableColumn(field)">新增列</a-button>
                        </a-space>
                        <a-table
                          :columns="getTableColumns(field)"
                          :data-source="getTableRows(field)"
                          :pagination="false"
                          size="small"
                          row-key="__rowKey"
                        >
                          <template #bodyCell="{ column, record, index }">
                            <template v-if="column.key === 'action'">
                              <a-button danger size="small" @click="removeTableRow(field, index)">删除</a-button>
                            </template>
                            <template v-else>
                              <a-input
                                :value="String(record[column.dataIndex] ?? '')"
                                @update:value="(val: string) => updateTableCell(field, index, String(column.dataIndex), val)"
                              />
                            </template>
                          </template>
                        </a-table>
                      </a-space>
                    </template>

                    <template v-else>
                      <a-input
                        :value="String(getFieldValue(field) ?? '')"
                        @update:value="(val: string) => updateFieldValue(field, val)"
                      />
                    </template>
                  </a-form-item>
                </template>
                <template v-else>
                  <a-form-item label="配置 JSON（Schema 不可用时可直接编辑）" style="margin-bottom: 0">
                    <a-textarea
                      v-model:value="editForm.configText"
                      :rows="12"
                      placeholder="请输入 JSON 对象配置"
                    />
                  </a-form-item>
                </template>
              </a-card>
            </a-form>
          </template>

            <a-empty v-else description="请选择左侧实例进行编辑" />
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-modal
      v-model:open="addModalVisible"
      title="新增插件实例"
      @ok="submitAdd"
      :confirm-loading="submitting"
      width="520px"
    >
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="插件名" required>
              <a-select v-model:value="addForm.plugin" placeholder="请选择插件">
                <a-select-option v-for="name in discoveredPlugins" :key="name" :value="name">
                  {{ name }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="实例名称">
              <a-input v-model:value="addForm.name" placeholder="可选" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="启用">
          <a-switch v-model:checked="addForm.enabled" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="jsonPreviewVisible" title="当前配置 JSON" width="760px" :footer="null">
      <a-textarea :value="jsonPreviewText" :rows="18" readonly />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import axios from 'axios'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api'

interface PluginInstance {
  id: string
  plugin: string
  enabled: boolean
  name: string
  config: Record<string, unknown>
}

interface PluginSchemaField {
  type: string
  format?: string
  default?: unknown
  required?: boolean
  description?: string
  item_type?: string
}

interface PluginsGetResponse {
  code: number
  status: string
  message: string
  version: number
  discovered_plugins: string[]
  schemas: Record<string, Record<string, PluginSchemaField>>
  schema_errors: Record<string, string>
  instances: PluginInstance[]
  runtime_states: Record<string, PluginRuntimeState>
}

interface PluginRuntimeState {
  instance_id: string
  plugin: string
  status: string
  generation: number
  lifecycle_phase: string
  lifecycle_updated_at?: string | null
  reload_count: number
  last_reload_reason?: string | null
  last_reload_at?: string | null
  created_at?: string | null
  discovered_at?: string | null
  loaded_at?: string | null
  activated_at?: string | null
  disposed_at?: string | null
  unloaded_at?: string | null
  last_error?: string | null
  last_error_at?: string | null
}

interface ListRow {
  __rowKey: string
  value: unknown
}

interface KeyValueRow {
  __rowKey: string
  key: string
  value: string
}

interface TableRow {
  __rowKey: string
  [key: string]: unknown
}

interface TableColumn {
  title: string
  dataIndex: string
  key: string
}

const logger = window.electronAPI.getLogger('插件管理调试页')
const loading = ref(false)
const submitting = ref(false)
const reloadingAll = ref(false)
const keyword = ref('')

const version = ref(1)
const discoveredPlugins = ref<string[]>([])
const schemaMap = ref<Record<string, Record<string, PluginSchemaField>>>({})
const schemaErrors = ref<Record<string, string>>({})
const instances = ref<PluginInstance[]>([])
const runtimeStates = ref<Record<string, PluginRuntimeState>>({})
const selectedInstanceId = ref('')
const editSnapshot = ref('')

const addModalVisible = ref(false)
const jsonPreviewVisible = ref(false)

const listColumns: TableColumn[] = [
  { title: '值', dataIndex: 'value', key: 'value' },
  { title: '操作', dataIndex: 'action', key: 'action' },
]

const keyValueColumns: TableColumn[] = [
  { title: '键', dataIndex: 'key', key: 'key' },
  { title: '值', dataIndex: 'value', key: 'value' },
  { title: '操作', dataIndex: 'action', key: 'action' },
]

const addForm = reactive({
  plugin: '',
  name: '',
  enabled: true,
})

const editForm = reactive({
  instanceId: '',
  plugin: '',
  name: '',
  enabled: true,
  configText: '{}',
})

const selectedInstance = computed(() =>
  instances.value.find(item => item.id === selectedInstanceId.value)
)

const selectedRuntimeState = computed(() => {
  if (!selectedInstanceId.value) {
    return null
  }
  return runtimeStates.value[selectedInstanceId.value] || null
})

const activeSchema = computed(() => {
  const pluginName = editForm.plugin || selectedInstance.value?.plugin
  if (!pluginName) {
    return {}
  }
  return schemaMap.value[pluginName] || {}
})

const hasEnableSchema = (pluginName?: string) => {
  if (!pluginName) {
    return false
  }
  const schema = schemaMap.value[pluginName]
  return Boolean(schema && schema.enable && schema.enable.type === 'boolean')
}

const activeSchemaEntries = computed(() =>
  Object.entries(activeSchema.value).filter(([field, fieldSchema]) => {
    if (field === 'enable' && fieldSchema.type === 'boolean') {
      return false
    }
    return true
  })
)

const currentSchemaError = computed(() => {
  if (!editForm.plugin) {
    return ''
  }
  return schemaErrors.value[editForm.plugin] || ''
})

const filteredInstances = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) {
    return instances.value
  }
  return instances.value.filter(item => {
    return (
      item.id.toLowerCase().includes(kw) ||
      item.plugin.toLowerCase().includes(kw) ||
      (item.name || '').toLowerCase().includes(kw)
    )
  })
})

const isDirty = computed(() => {
  if (!selectedInstance.value) {
    return false
  }
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

const parseConfigText = (text: string): Record<string, unknown> => {
  const parsed = JSON.parse(text)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('配置必须是 JSON 对象')
  }
  return parsed as Record<string, unknown>
}

const getRuntimeState = (instanceId: string) => runtimeStates.value[instanceId]

const getStatusTagColor = (status?: string) => {
  if (!status) {
    return 'default'
  }
  if (status === 'active') {
    return 'success'
  }
  if (status === 'error') {
    return 'error'
  }
  if (status === 'loaded') {
    return 'processing'
  }
  if (status === 'disposed' || status === 'unloaded') {
    return 'default'
  }
  if (status === 'configured' || status === 'discovered') {
    return 'warning'
  }
  return 'default'
}

const getPhaseTagColor = (phase?: string) => {
  if (!phase) {
    return 'default'
  }
  if (phase === 'active') {
    return 'green'
  }
  if (phase === 'reload_failed' || phase === 'on_reload_rollback') {
    return 'red'
  }
  if (phase === 'on_reload_prepare' || phase === 'on_reload_commit') {
    return 'cyan'
  }
  if (phase === 'on_load' || phase === 'on_start') {
    return 'blue'
  }
  if (phase === 'on_stop' || phase === 'on_unload' || phase === 'disposed' || phase === 'unloaded') {
    return 'default'
  }
  return 'geekblue'
}

const formatRuntimeTime = (value?: string | null) => {
  if (!value) {
    return '-'
  }
  const ts = Date.parse(value)
  if (Number.isNaN(ts)) {
    return value
  }
  return new Date(ts).toLocaleString()
}

const getConfigObjectFromText = () => parseConfigText(editForm.configText)

const setConfigObjectToText = (config: Record<string, unknown>) => {
  editForm.configText = JSON.stringify(config, null, 2)
}

const openJsonPreview = () => {
  jsonPreviewVisible.value = true
}

const getFieldValue = (field: string) => {
  try {
    const config = getConfigObjectFromText()
    return config[field]
  } catch {
    return undefined
  }
}

const getBooleanValue = (field: string) => Boolean(getFieldValue(field))

const getNumberValue = (field: string) => {
  const value = getFieldValue(field)
  if (typeof value === 'number') {
    return value
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const numberValue = Number(value)
    return Number.isFinite(numberValue) ? numberValue : undefined
  }
  return undefined
}

const isPasswordSchema = (fieldSchema: PluginSchemaField) =>
  fieldSchema.type === 'string' && fieldSchema.format === 'password'

const getTypeLabel = (fieldSchema: PluginSchemaField) => {
  if (isPasswordSchema(fieldSchema)) {
    return '密码'
  }
  if (fieldSchema.type === 'string') {
    return '字符串'
  }
  if (fieldSchema.type === 'number') {
    return '数字'
  }
  if (fieldSchema.type === 'boolean') {
    return '布尔'
  }
  if (fieldSchema.type === 'list') {
    return '列表'
  }
  if (fieldSchema.type === 'key_value') {
    return '键值对'
  }
  if (fieldSchema.type === 'table') {
    return '表格'
  }
  return fieldSchema.type
}

const updateFieldValue = (field: string, value: unknown) => {
  try {
    const config = getConfigObjectFromText()
    config[field] = value as never
    setConfigObjectToText(config)
  } catch (error) {
    message.error(`更新字段失败: ${String(error)}`)
  }
}

const normalizeListValueByType = (value: unknown, itemType?: string) => {
  if (itemType === 'number') {
    if (typeof value === 'number') {
      return value
    }
    const numberValue = Number(value)
    return Number.isFinite(numberValue) ? numberValue : 0
  }
  if (itemType === 'boolean') {
    return Boolean(value)
  }
  return String(value ?? '')
}

const getListRows = (field: string): ListRow[] => {
  const value = getFieldValue(field)
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item, index) => ({
    __rowKey: `${field}-${index}`,
    value: item,
  }))
}

const addListRow = (field: string, itemType?: string) => {
  const value = getFieldValue(field)
  const list = Array.isArray(value) ? [...value] : []
  if (itemType === 'number') {
    list.push(0)
  } else if (itemType === 'boolean') {
    list.push(false)
  } else {
    list.push('')
  }
  updateFieldValue(field, list)
}

const removeListRow = (field: string, index: number) => {
  const value = getFieldValue(field)
  const list = Array.isArray(value) ? [...value] : []
  list.splice(index, 1)
  updateFieldValue(field, list)
}

const updateListRowValue = (field: string, index: number, value: unknown, itemType?: string) => {
  const raw = getFieldValue(field)
  const list = Array.isArray(raw) ? [...raw] : []
  list[index] = normalizeListValueByType(value, itemType)
  updateFieldValue(field, list)
}

const getKeyValueRows = (field: string): KeyValueRow[] => {
  const value = getFieldValue(field)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }
  return Object.entries(value as Record<string, unknown>).map(([key, item], index) => ({
    __rowKey: `${field}-${index}`,
    key,
    value: String(item ?? ''),
  }))
}

const addKeyValueRow = (field: string) => {
  const value = getFieldValue(field)
  const obj = value && typeof value === 'object' && !Array.isArray(value)
    ? { ...(value as Record<string, unknown>) }
    : {}

  let idx = 1
  let key = `key_${idx}`
  while (Object.prototype.hasOwnProperty.call(obj, key)) {
    idx += 1
    key = `key_${idx}`
  }

  obj[key] = ''
  updateFieldValue(field, obj)
}

const removeKeyValueRow = (field: string, key: string) => {
  const value = getFieldValue(field)
  const obj = value && typeof value === 'object' && !Array.isArray(value)
    ? { ...(value as Record<string, unknown>) }
    : {}
  delete obj[key]
  updateFieldValue(field, obj)
}

const updateKeyValueRowKey = (field: string, oldKey: string, newKey: string) => {
  const safeKey = newKey.trim()
  if (!safeKey || safeKey === oldKey) {
    return
  }

  const value = getFieldValue(field)
  const obj = value && typeof value === 'object' && !Array.isArray(value)
    ? { ...(value as Record<string, unknown>) }
    : {}

  if (Object.prototype.hasOwnProperty.call(obj, safeKey)) {
    message.warning('键名已存在')
    return
  }

  obj[safeKey] = obj[oldKey]
  delete obj[oldKey]
  updateFieldValue(field, obj)
}

const updateKeyValueRowValue = (field: string, key: string, value: string) => {
  const source = getFieldValue(field)
  const obj = source && typeof source === 'object' && !Array.isArray(source)
    ? { ...(source as Record<string, unknown>) }
    : {}
  obj[key] = value
  updateFieldValue(field, obj)
}

const getTableRows = (field: string): TableRow[] => {
  const value = getFieldValue(field)
  if (!Array.isArray(value)) {
    return []
  }

  return value.map((item, index) => {
    const row = item && typeof item === 'object' && !Array.isArray(item)
      ? { ...(item as Record<string, unknown>) }
      : {}
    return {
      __rowKey: `${field}-${index}`,
      ...row,
    }
  })
}

const getTableColumns = (field: string): TableColumn[] => {
  const rows = getTableRows(field)
  const keys = new Set<string>()

  rows.forEach(row => {
    Object.keys(row).forEach(key => {
      if (key !== '__rowKey') {
        keys.add(key)
      }
    })
  })

  if (keys.size === 0) {
    keys.add('col_1')
  }

  const columns: TableColumn[] = Array.from(keys).map(key => ({
    title: key,
    dataIndex: key,
    key,
  }))

  columns.push({
    title: '操作',
    dataIndex: 'action',
    key: 'action',
  })

  return columns
}

const addTableRow = (field: string) => {
  const rows = getTableRows(field)
  const columns = getTableColumns(field)
  const row: Record<string, unknown> = {}

  columns.forEach(col => {
    if (col.key !== 'action') {
      row[col.key] = ''
    }
  })

  rows.push({ __rowKey: `${field}-${Date.now()}`, ...row })
  const next = rows.map(({ __rowKey, ...rest }) => rest)
  updateFieldValue(field, next)
}

const removeTableRow = (field: string, index: number) => {
  const rows = getTableRows(field)
  rows.splice(index, 1)
  const next = rows.map(({ __rowKey, ...rest }) => rest)
  updateFieldValue(field, next)
}

const addTableColumn = (field: string) => {
  const columnName = window.prompt('请输入列名')
  if (!columnName) {
    return
  }

  const col = columnName.trim()
  if (!col) {
    return
  }

  const rows = getTableRows(field)
  if (rows.length === 0) {
    rows.push({
      __rowKey: `${field}-${Date.now()}`,
      [col]: '',
    })
    const first = rows.map(({ __rowKey, ...rest }) => rest)
    updateFieldValue(field, first)
    return
  }

  rows.forEach(row => {
    if (!Object.prototype.hasOwnProperty.call(row, col)) {
      row[col] = ''
    }
  })

  const next = rows.map(({ __rowKey, ...rest }) => rest)
  updateFieldValue(field, next)
}

const updateTableCell = (field: string, index: number, key: string, value: string) => {
  const rows = getTableRows(field)
  if (!rows[index]) {
    return
  }

  rows[index][key] = value
  const next = rows.map(({ __rowKey, ...rest }) => rest)
  updateFieldValue(field, next)
}

const setEditFromInstance = (row: PluginInstance) => {
  editForm.instanceId = row.id
  editForm.plugin = row.plugin
  editForm.name = row.name
  editForm.enabled = row.enabled
  const nextConfig = { ...(row.config || {}) }
  if (hasEnableSchema(row.plugin)) {
    nextConfig.enable = row.enabled
  }
  editForm.configText = JSON.stringify(nextConfig, null, 2)
  editSnapshot.value = JSON.stringify({
    instanceId: editForm.instanceId,
    plugin: editForm.plugin,
    name: editForm.name,
    enabled: editForm.enabled,
    configText: editForm.configText,
  })
}

const selectInstance = (instanceId: string) => {
  selectedInstanceId.value = instanceId
  const target = instances.value.find(item => item.id === instanceId)
  if (target) {
    setEditFromInstance(target)
  }
}

const apiPost = async <T = any>(url: string, payload: Record<string, unknown> = {}) => {
  const requestUrl = `${OpenAPI.BASE}${url}`
  const { data } = await axios.post<T>(requestUrl, payload)
  return data
}

const fetchData = async () => {
  loading.value = true
  try {
    const data = await apiPost<PluginsGetResponse>('/api/plugins/get', {})
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '获取插件配置失败')
    }

    version.value = data.version
    discoveredPlugins.value = data.discovered_plugins
    schemaMap.value = data.schemas || {}
    schemaErrors.value = data.schema_errors || {}
    instances.value = data.instances
    runtimeStates.value = data.runtime_states || {}

    if (!selectedInstanceId.value && instances.value.length > 0) {
      selectInstance(instances.value[0].id)
      return
    }

    if (selectedInstanceId.value) {
      const target = instances.value.find(item => item.id === selectedInstanceId.value)
      if (target) {
        setEditFromInstance(target)
      } else if (instances.value.length > 0) {
        selectInstance(instances.value[0].id)
      } else {
        selectedInstanceId.value = ''
      }
    }
  } catch (error) {
    message.error(`获取失败: ${String(error)}`)
    logger.error(`获取插件配置失败: ${String(error)}`)
  } finally {
    loading.value = false
  }
}

const openAddModal = () => {
  addForm.plugin = discoveredPlugins.value[0] || ''
  addForm.name = ''
  addForm.enabled = true
  addModalVisible.value = true
}

const submitAdd = async () => {
  submitting.value = true
  try {
    const data = await apiPost('/api/plugins/add', {
      plugin: addForm.plugin,
      name: addForm.name || undefined,
      enabled: addForm.enabled,
      config: {},
    })
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '新增失败')
    }
    message.success('新增成功')
    addModalVisible.value = false
    await fetchData()
    if (data.instance?.id) {
      selectInstance(data.instance.id)
    }
  } catch (error) {
    message.error(`新增失败: ${String(error)}`)
  } finally {
    submitting.value = false
  }
}

const resetEdit = () => {
  const target = selectedInstance.value
  if (!target) {
    return
  }
  setEditFromInstance(target)
}

const submitEdit = async () => {
  submitting.value = true
  try {
    const config = parseConfigText(editForm.configText)
    if (hasEnableSchema(editForm.plugin)) {
      config.enable = editForm.enabled
      setConfigObjectToText(config)
    }
    const data = await apiPost('/api/plugins/update', {
      instanceId: editForm.instanceId,
      plugin: editForm.plugin,
      name: editForm.name,
      enabled: editForm.enabled,
      config,
    })
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '更新失败')
    }
    message.success('更新成功')
    await fetchData()
  } catch (error) {
    message.error(`更新失败: ${String(error)}`)
  } finally {
    submitting.value = false
  }
}

const deleteInstance = async (instanceId: string) => {
  try {
    const data = await apiPost('/api/plugins/delete', { instanceId })
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '删除失败')
    }
    message.success('删除成功')
    await fetchData()
    if (selectedInstanceId.value === instanceId) {
      selectedInstanceId.value = instances.value[0]?.id || ''
      if (selectedInstanceId.value) {
        selectInstance(selectedInstanceId.value)
      }
    }
  } catch (error) {
    message.error(`删除失败: ${String(error)}`)
  }
}

const reloadAll = async () => {
  reloadingAll.value = true
  try {
    const data = await apiPost('/api/plugins/reload', {})
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '重载失败')
    }
    message.success('重载全部成功')
    await fetchData()
  } catch (error) {
    message.error(`重载失败: ${String(error)}`)
  } finally {
    reloadingAll.value = false
  }
}

const reloadInstance = async (instanceId: string) => {
  try {
    const data = await apiPost('/api/plugins/reload_instance', { instanceId })
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '重载实例失败')
    }
    message.success(`实例重载成功: ${instanceId}`)
    await fetchData()
    if (selectedInstanceId.value) {
      selectInstance(selectedInstanceId.value)
    }
  } catch (error) {
    message.error(`实例重载失败: ${String(error)}`)
  }
}

const reloadPlugin = async (plugin: string) => {
  try {
    const data = await apiPost('/api/plugins/reload_plugin', { plugin })
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '重载插件失败')
    }
    message.success(`插件重载成功: ${plugin}`)
    await fetchData()
    if (selectedInstanceId.value) {
      selectInstance(selectedInstanceId.value)
    }
  } catch (error) {
    message.error(`插件重载失败: ${String(error)}`)
  }
}

const toggleInstanceEnabled = async (instance: PluginInstance, enabled: boolean) => {
  const previous = instance.enabled
  instance.enabled = enabled

  try {
    const data = await apiPost('/api/plugins/update', {
      instanceId: instance.id,
      enabled,
    })
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '更新启用状态失败')
    }

    if (selectedInstanceId.value === instance.id) {
      editForm.enabled = enabled
      if (hasEnableSchema(editForm.plugin)) {
        updateFieldValue('enable', enabled)
      }
    }
  } catch (error) {
    instance.enabled = previous
    message.error(`更新启用状态失败: ${String(error)}`)
  }
}

onMounted(() => {
  void fetchData()
})
</script>

<style scoped>
.plugin-dev-page {
  padding: 16px;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.scripts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.section-card {
  margin-bottom: 0;
}

.main-layout {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  align-items: stretch;
}

.main-layout :deep(.ant-col) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.left-panel {
  position: sticky;
  top: 0;
  height: 100%;
}

.list-card {
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
}

.list-card :deep(.ant-card-body) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.search-box {
  margin-bottom: 10px;
}

.instance-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.detail-card {
  height: 100%;
  min-width: 0;
  border-radius: 12px;
  overflow: hidden;
}

.detail-card :deep(.ant-card-head) {
  min-height: 56px;
  padding-inline: 16px;
}

.detail-card :deep(.ant-card-head-title) {
  padding: 12px 0;
}

.detail-card :deep(.ant-card-extra) {
  padding: 8px 0;
}

.detail-card :deep(.ant-card-body) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 16px;
}

.detail-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 2px;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.detail-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.detail-scroll :deep(.ant-table-wrapper),
.detail-scroll :deep(.ant-table-container),
.detail-scroll :deep(.ant-table-content) {
  max-width: 100%;
  overflow-x: hidden !important;
}

.detail-scroll :deep(.ant-table) {
  width: 100%;
  table-layout: fixed;
}

.detail-scroll :deep(.ant-table-cell) {
  white-space: normal;
  word-break: break-word;
}

.instance-item {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 10px;
  cursor: pointer;
  background: var(--ant-color-bg-container);
  transition: all 0.2s ease;
}

.instance-item.active {
  border-color: var(--ant-color-primary);
  background: linear-gradient(135deg, var(--ant-color-primary-bg), color-mix(in srgb, var(--ant-color-primary-bg) 80%, white));
  box-shadow: 0 4px 16px color-mix(in srgb, var(--ant-color-primary) 12%, transparent);
}

.instance-item:hover {
  border-color: var(--ant-color-primary-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
}

.instance-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.instance-name {
  font-weight: 600;
}

.instance-plugin,
.instance-id {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.instance-runtime {
  margin-top: 8px;
}

.runtime-observer-card {
  margin-bottom: 10px;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.editor-card {
  margin-bottom: 10px;
}

.schema-field-head {
  margin-bottom: 6px;
}

.type-tag {
  font-weight: 500;
}

.schema-item :deep(.ant-form-item-control-input-content) {
  border-radius: 8px;
  padding: 6px 8px;
}

.schema-item-boolean :deep(.ant-form-item-control-input-content) {
  background: var(--ant-color-success-bg);
}

.schema-item-string :deep(.ant-form-item-control-input-content) {
  background: var(--ant-color-info-bg);
}

.schema-item-number :deep(.ant-form-item-control-input-content) {
  background: var(--ant-color-warning-bg);
}

.schema-item-list :deep(.ant-form-item-control-input-content),
.schema-item-key_value :deep(.ant-form-item-control-input-content),
.schema-item-table :deep(.ant-form-item-control-input-content) {
  background: var(--ant-color-fill-tertiary);
}

.detail-card :deep(.ant-alert) {
  border-radius: 10px;
}

.detail-card :deep(.ant-form-item) {
  margin-bottom: 14px;
}

.detail-card :deep(.ant-table-wrapper) {
  border-radius: 10px;
  overflow: hidden;
}

.detail-card :deep(.ant-card-small > .ant-card-body) {
  padding: 14px;
}
</style>
