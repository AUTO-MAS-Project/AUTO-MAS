<template>
  <div class="oknte-config-editor">
    <div class="editor-header">
      <h3>OK-NTE 配置编辑</h3>
      <a-tag v-if="hasChanges" color="warning">有未保存的更改</a-tag>
      <a-tag v-else color="success">已保存</a-tag>
    </div>

    <a-spin :spinning="loading" tip="加载配置中...">
      <a-row :gutter="24" class="editor-layout">
        <!-- 左侧：配置文件列表 -->
        <a-col :span="8" class="left-panel">
          <div class="config-groups">
            <div v-for="(group, groupName) in groupedConfigs" :key="groupName" class="config-group">
              <div class="group-header">{{ groupName }}</div>
              <div class="group-items">
                <div
                  v-for="config in group"
                  :key="config.filename"
                  class="config-item"
                  :class="{
                    'config-item--active': selectedFilename === config.filename,
                    'config-item--changed': changedFiles.has(config.filename),
                  }"
                  @click="selectConfig(config.filename)"
                >
                  <div class="config-item-info">
                    <span class="config-item-name">{{ config.displayName }}</span>
                    <span v-if="config.taskIndex" class="config-item-badge">
                      -t {{ config.taskIndex }}
                    </span>
                  </div>
                  <span v-if="changedFiles.has(config.filename)" class="config-item-dot" />
                </div>
              </div>
            </div>
          </div>
        </a-col>

        <!-- 右侧：配置表单 -->
        <a-col :span="16" class="right-panel">
          <div v-if="selectedConfig" class="config-form">
            <div class="form-header">
              <h4>{{ selectedConfig.displayName }}</h4>
              <span class="form-filename">{{ selectedConfigFilename }}</span>
            </div>

            <a-form layout="vertical" class="form-fields">
              <a-form-item
                v-for="field in selectedConfig.fields"
                :key="field.name"
                :label="field.label || field.name"
              >
                <template v-if="field.description" #extra>
                  {{ field.description }}
                </template>

                <!-- object 类型：子任务配置组 -->
                <template v-if="field.type === 'object'">
                  <div class="object-field">
                    <a-empty
                      v-if="!field.children || field.children.length === 0"
                      description="该子任务暂无可编辑字段"
                    />
                    <a-form-item
                      v-for="child in field.children || []"
                      :key="`${field.name}.${child.name}`"
                      :label="child.label || child.name"
                      class="nested-form-item"
                    >
                      <template v-if="child.description" #extra>
                        {{ child.description }}
                      </template>

                      <a-switch
                        v-if="child.type === 'bool'"
                        :checked="getNestedFieldValue(selectedConfigFilename, field.name, child)"
                        @change="
                          (val: boolean) =>
                            setNestedFieldValue(selectedConfigFilename, field.name, child, val)
                        "
                      />

                      <a-select
                        v-else-if="child.type === 'select'"
                        :value="getNestedFieldValue(selectedConfigFilename, field.name, child)"
                        style="width: 100%"
                        @change="
                          (val: string) =>
                            setNestedFieldValue(selectedConfigFilename, field.name, child, val)
                        "
                      >
                        <a-select-option v-for="opt in child.options || []" :key="opt" :value="opt">
                          {{ getOptionLabel(opt) }}
                        </a-select-option>
                      </a-select>

                      <a-select
                        v-else-if="child.type === 'list'"
                        :value="getNestedFieldValue(selectedConfigFilename, field.name, child)"
                        mode="multiple"
                        style="width: 100%"
                        placeholder="请选择"
                        @change="
                          (val: string[]) =>
                            setNestedFieldValue(selectedConfigFilename, field.name, child, val)
                        "
                      >
                        <a-select-option v-for="opt in child.options || []" :key="opt" :value="opt">
                          {{ getOptionLabel(opt) }}
                        </a-select-option>
                      </a-select>

                      <a-input-number
                        v-else-if="child.type === 'int'"
                        :value="getNestedFieldValue(selectedConfigFilename, field.name, child)"
                        :min="child.min"
                        :max="child.max"
                        style="width: 100%"
                        @change="
                          (val: number | null) => {
                            if (val !== null)
                              setNestedFieldValue(selectedConfigFilename, field.name, child, val)
                          }
                        "
                      />

                      <a-input-number
                        v-else-if="child.type === 'float'"
                        :value="getNestedFieldValue(selectedConfigFilename, field.name, child)"
                        :min="child.min"
                        :max="child.max"
                        :step="child.step || 0.1"
                        style="width: 100%"
                        @change="
                          (val: number | null) => {
                            if (val !== null)
                              setNestedFieldValue(selectedConfigFilename, field.name, child, val)
                          }
                        "
                      />

                      <a-input
                        v-else
                        :value="getNestedFieldValue(selectedConfigFilename, field.name, child)"
                        style="width: 100%"
                        @change="
                          (e: Event) =>
                            setNestedFieldValue(
                              selectedConfigFilename,
                              field.name,
                              child,
                              (e.target as HTMLInputElement).value
                            )
                        "
                      />
                    </a-form-item>
                  </div>
                </template>

                <!-- routine_items 类型：新版日常任务流程 -->
                <template v-else-if="field.type === 'routine_items'">
                  <div class="routine-items">
                    <div
                      v-for="(item, index) in getRoutineItemValues(selectedConfigFilename, field)"
                      :key="item.id"
                      class="routine-item"
                    >
                      <a-checkbox
                        :checked="item.enabled"
                        @change="
                          (event: any) =>
                            setRoutineItemEnabled(
                              selectedConfigFilename,
                              field,
                              item.id,
                              Boolean(event.target.checked)
                            )
                        "
                      />
                      <div class="routine-item-info">
                        <span class="routine-item-name">{{
                          getRoutineItemLabel(field, item.id)
                        }}</span>
                        <span class="routine-item-id">{{ item.id }}</span>
                      </div>
                      <a-space :size="4">
                        <a-button
                          size="small"
                          :disabled="index === 0"
                          aria-label="上移日常子任务"
                          @click="moveRoutineItem(selectedConfigFilename, field, index, -1)"
                        >
                          <template #icon>
                            <ArrowUpOutlined />
                          </template>
                        </a-button>
                        <a-button
                          size="small"
                          :disabled="
                            index === getRoutineItemValues(selectedConfigFilename, field).length - 1
                          "
                          aria-label="下移日常子任务"
                          @click="moveRoutineItem(selectedConfigFilename, field, index, 1)"
                        >
                          <template #icon>
                            <ArrowDownOutlined />
                          </template>
                        </a-button>
                      </a-space>
                    </div>
                  </div>
                </template>

                <!-- bool 类型：开关 -->
                <a-switch
                  v-else-if="field.type === 'bool'"
                  :checked="getFieldValue(selectedConfigFilename, field.name, field.value)"
                  @change="(val: boolean) => setFieldValue(selectedConfigFilename, field.name, val)"
                />

                <!-- select 类型：下拉选择 -->
                <a-select
                  v-else-if="field.type === 'select'"
                  :value="getFieldValue(selectedConfigFilename, field.name, field.value)"
                  style="width: 100%"
                  @change="(val: string) => setFieldValue(selectedConfigFilename, field.name, val)"
                >
                  <a-select-option v-for="opt in field.options || []" :key="opt" :value="opt">
                    {{ getOptionLabel(opt) }}
                  </a-select-option>
                </a-select>

                <!-- list 类型：多选 -->
                <a-select
                  v-else-if="field.type === 'list'"
                  :value="getFieldValue(selectedConfigFilename, field.name, field.value)"
                  mode="multiple"
                  style="width: 100%"
                  placeholder="请选择"
                  @change="
                    (val: string[]) => setFieldValue(selectedConfigFilename, field.name, val)
                  "
                >
                  <a-select-option v-for="opt in field.options || []" :key="opt" :value="opt">
                    {{ getOptionLabel(opt) }}
                  </a-select-option>
                </a-select>

                <!-- int 类型：整数输入 -->
                <a-input-number
                  v-else-if="field.type === 'int'"
                  :value="getFieldValue(selectedConfigFilename, field.name, field.value)"
                  :min="field.min"
                  :max="field.max"
                  style="width: 100%"
                  @change="
                    (val: number | null) => {
                      if (val !== null) setFieldValue(selectedConfigFilename, field.name, val)
                    }
                  "
                />

                <!-- float 类型：浮点数输入 -->
                <a-input-number
                  v-else-if="field.type === 'float'"
                  :value="getFieldValue(selectedConfigFilename, field.name, field.value)"
                  :min="field.min"
                  :max="field.max"
                  :step="field.step || 0.1"
                  style="width: 100%"
                  @change="
                    (val: number | null) => {
                      if (val !== null) setFieldValue(selectedConfigFilename, field.name, val)
                    }
                  "
                />

                <!-- hotkey 类型：快捷键输入 -->
                <a-input
                  v-else-if="field.type === 'hotkey'"
                  :value="getFieldValue(selectedConfigFilename, field.name, field.value)"
                  style="width: 100%"
                  @change="
                    (e: Event) =>
                      setFieldValue(
                        selectedConfigFilename,
                        field.name,
                        (e.target as HTMLInputElement).value
                      )
                  "
                />

                <!-- string 类型：文本输入 -->
                <a-input
                  v-else
                  :value="getFieldValue(selectedConfigFilename, field.name, field.value)"
                  style="width: 100%"
                  @change="
                    (e: Event) =>
                      setFieldValue(
                        selectedConfigFilename,
                        field.name,
                        (e.target as HTMLInputElement).value
                      )
                  "
                />
              </a-form-item>

              <div v-if="selectedConfig.fields.length === 0" class="empty-fields">
                <a-empty description="该配置文件暂无可编辑的字段" />
              </div>
            </a-form>
          </div>

          <div v-else class="no-selection">
            <a-empty description="请从左侧选择一个配置文件" />
          </div>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons-vue'
import { OknteService } from '@/api/services/OknteService'

interface RoutineItemDefinition {
  id: string
  label: string
  exclusiveGroup: string | null
  defaultEnabled?: boolean
}

interface RoutineItemValue {
  id: string
  enabled: boolean
}

interface ConfigField {
  name: string
  type: string
  label: string
  description: string
  value: any
  options: string[] | null
  children?: ConfigField[] | null
  itemDefinitions?: RoutineItemDefinition[] | null
  min: number | null
  max: number | null
  step: number | null
}

interface ConfigFile {
  filename: string
  displayName: string
  group: string
  taskIndex: number | null
  fieldCount: number
  fields: ConfigField[]
  currentData: Record<string, any>
}

const props = defineProps<{
  scriptId: string
  userId: string
  refreshToken?: number
}>()

const emit = defineEmits<{
  saved: []
}>()

const logger = window.electronAPI.getLogger('OK-NTE配置编辑')

const loading = ref(false)
const saving = ref(false)
const configs = ref<ConfigFile[]>([])
const selectedFilename = ref<string | null>(null)
const changedFiles = ref(new Set<string>())
const localChanges = ref<Record<string, Record<string, any>>>({})
const optionLabels = ref<Record<string, string>>({})

const groupedConfigs = computed(() => {
  const groups: Record<string, ConfigFile[]> = {}
  for (const config of configs.value) {
    const group = config.group || '其他'
    if (!groups[group]) groups[group] = []
    groups[group].push(config)
  }
  return groups
})

const selectedConfig = computed(() => {
  if (!selectedFilename.value) return null
  return configs.value.find(c => c.filename === selectedFilename.value) || null
})

const selectedConfigFilename = computed(() => selectedConfig.value?.filename || '')

const hasChanges = computed(() => changedFiles.value.size > 0)

const getOptionLabel = (value: string) => {
  return optionLabels.value[value] || value
}

const getFieldValue = (filename: string, fieldName: string, fallback: any) => {
  if (localChanges.value[filename] && localChanges.value[filename][fieldName] !== undefined) {
    return localChanges.value[filename][fieldName]
  }
  return fallback
}

const cleanupFileChanges = (filename: string) => {
  if (localChanges.value[filename] && Object.keys(localChanges.value[filename]).length === 0) {
    delete localChanges.value[filename]
    changedFiles.value.delete(filename)
  }
}

const setFieldValue = (filename: string, fieldName: string, value: any) => {
  if (!localChanges.value[filename]) {
    localChanges.value[filename] = {}
  }

  // 比较原始值
  const config = configs.value.find(c => c.filename === filename)
  const field = config?.fields.find(f => f.name === fieldName)
  const originalValue = field?.value

  if (JSON.stringify(value) === JSON.stringify(originalValue)) {
    delete localChanges.value[filename][fieldName]
    cleanupFileChanges(filename)
  } else {
    localChanges.value[filename][fieldName] = value
    changedFiles.value.add(filename)
  }
  // 触发响应式更新
  changedFiles.value = new Set(changedFiles.value)
}

const getNestedFieldValue = (filename: string, groupName: string, child: ConfigField) => {
  const groupChanges = localChanges.value[filename]?.[groupName]
  if (groupChanges && typeof groupChanges === 'object' && groupChanges[child.name] !== undefined) {
    return groupChanges[child.name]
  }
  return child.value
}

const setNestedFieldValue = (
  filename: string,
  groupName: string,
  child: ConfigField,
  value: any
) => {
  if (!localChanges.value[filename]) {
    localChanges.value[filename] = {}
  }
  if (
    !localChanges.value[filename][groupName] ||
    typeof localChanges.value[filename][groupName] !== 'object'
  ) {
    localChanges.value[filename][groupName] = {}
  }

  const groupChanges = localChanges.value[filename][groupName]
  if (JSON.stringify(value) === JSON.stringify(child.value)) {
    delete groupChanges[child.name]
    if (Object.keys(groupChanges).length === 0) {
      delete localChanges.value[filename][groupName]
    }
    cleanupFileChanges(filename)
  } else {
    groupChanges[child.name] = value
    changedFiles.value.add(filename)
  }

  changedFiles.value = new Set(changedFiles.value)
}

const normalizeRoutineItems = (field: ConfigField, rawValue: any): RoutineItemValue[] => {
  const definitions = field.itemDefinitions || []
  const rawItems = Array.isArray(rawValue) ? rawValue : []
  const result: RoutineItemValue[] = []
  const seen = new Set<string>()

  for (const item of rawItems) {
    if (item && typeof item === 'object' && typeof item.id === 'string' && !seen.has(item.id)) {
      result.push({ id: item.id, enabled: Boolean(item.enabled) })
      seen.add(item.id)
    }
  }

  for (const definition of definitions) {
    if (!seen.has(definition.id)) {
      result.push({
        id: definition.id,
        enabled: Boolean(definition.defaultEnabled),
      })
    }
  }

  const enabledGroups = new Set<string>()
  return result.map(item => {
    const definition = definitions.find(candidate => candidate.id === item.id)
    const exclusiveGroup = definition?.exclusiveGroup
    if (!exclusiveGroup || !item.enabled) return item
    if (enabledGroups.has(exclusiveGroup)) {
      return { ...item, enabled: false }
    }
    enabledGroups.add(exclusiveGroup)
    return item
  })
}

const getRoutineItemValues = (filename: string, field: ConfigField) => {
  return normalizeRoutineItems(field, getFieldValue(filename, field.name, field.value))
}

const getRoutineItemDefinition = (field: ConfigField, itemId: string) => {
  return field.itemDefinitions?.find(item => item.id === itemId) || null
}

const getRoutineItemLabel = (field: ConfigField, itemId: string) => {
  return getRoutineItemDefinition(field, itemId)?.label || itemId
}

const setRoutineItemsValue = (filename: string, field: ConfigField, items: RoutineItemValue[]) => {
  setFieldValue(filename, field.name, normalizeRoutineItems(field, items))
}

const setRoutineItemEnabled = (
  filename: string,
  field: ConfigField,
  itemId: string,
  enabled: boolean
) => {
  const targetDefinition = getRoutineItemDefinition(field, itemId)
  const nextItems = getRoutineItemValues(filename, field).map(item => {
    const currentDefinition = getRoutineItemDefinition(field, item.id)
    if (item.id === itemId) {
      return { ...item, enabled }
    }
    if (
      enabled &&
      targetDefinition?.exclusiveGroup &&
      currentDefinition?.exclusiveGroup === targetDefinition.exclusiveGroup
    ) {
      return { ...item, enabled: false }
    }
    return item
  })
  setRoutineItemsValue(filename, field, nextItems)
}

const moveRoutineItem = (filename: string, field: ConfigField, index: number, offset: number) => {
  const items = getRoutineItemValues(filename, field)
  const nextIndex = index + offset
  if (nextIndex < 0 || nextIndex >= items.length) return
  const nextItems = [...items]
  const [item] = nextItems.splice(index, 1)
  nextItems.splice(nextIndex, 0, item)
  setRoutineItemsValue(filename, field, nextItems)
}

const selectConfig = (filename: string) => {
  selectedFilename.value = filename
}

const loadConfigs = async () => {
  if (!props.scriptId || !props.userId) return
  loading.value = true
  try {
    const resp = await OknteService.getOknteConfigsListApiScriptsOknteConfigsListPost(
      props.scriptId,
      props.userId
    )
    if (resp?.code === 200 && resp?.data) {
      const previousSelected = selectedFilename.value
      configs.value = resp.data
      optionLabels.value = resp.optionLabels || {}
      changedFiles.value = new Set()
      localChanges.value = {}

      if (configs.value.length === 0) {
        selectedFilename.value = null
      } else if (
        previousSelected &&
        configs.value.some(config => config.filename === previousSelected)
      ) {
        selectedFilename.value = previousSelected
      } else {
        selectedFilename.value = configs.value[0].filename
      }
    } else {
      message.error(resp?.message || '加载配置失败')
    }
  } catch (e) {
    logger.error(`加载配置失败: ${e instanceof Error ? e.message : String(e)}`)
    message.error('加载 OK-NTE 配置失败')
  } finally {
    loading.value = false
  }
}

const saveAll = async (silent = true) => {
  if (!hasChanges.value) return
  saving.value = true
  try {
    const configsToUpdate = { ...localChanges.value }
    const resp = await OknteService.batchUpdateOknteConfigsApiScriptsOknteConfigsBatchUpdatePost({
      script_id: props.scriptId,
      user_id: props.userId,
      configs: configsToUpdate,
    })
    if (resp?.code === 200) {
      changedFiles.value = new Set()
      localChanges.value = {}
      await loadConfigs()
      emit('saved')
      if (!silent) {
        message.success('配置已保存')
      }
    } else {
      message.error(resp?.message || '保存失败')
    }
  } catch (e) {
    logger.error(`保存配置失败: ${e instanceof Error ? e.message : String(e)}`)
    message.error('保存配置失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadConfigs()
})

onBeforeUnmount(async () => {
  if (hasChanges.value) {
    await saveAll(true)
  }
})

watch(
  () => [props.scriptId, props.userId, props.refreshToken],
  () => {
    if (props.scriptId && props.userId) {
      loadConfigs()
    }
  }
)
</script>

<style scoped>
.oknte-config-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.editor-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 12px;
}

.editor-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.editor-layout {
  min-height: 500px;
}

.left-panel {
  border-right: 1px solid var(--ant-color-border);
  padding-right: 24px;
  overflow-y: auto;
  max-height: 600px;
}

.config-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.group-header {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 8px 12px 4px;
}

.group-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.config-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  border-left: 3px solid transparent;
}

.config-item:hover {
  background-color: var(--ant-color-primary-bg-hover);
  border-left-color: var(--ant-color-primary);
}

.config-item--active {
  background-color: var(--ant-color-primary-bg) !important;
  border-left-color: var(--ant-color-primary) !important;
}

.config-item--changed {
  background-color: var(--ant-color-warning-bg);
}

.config-item-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.config-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.config-item-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--ant-color-fill-secondary);
  color: var(--ant-color-text-secondary);
}

.config-item-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ant-color-warning);
  flex-shrink: 0;
}

.right-panel {
  padding-left: 24px;
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.form-header h4 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.form-filename {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  font-family: monospace;
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-fields :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.form-fields :deep(.ant-form-item-label) {
  font-weight: 600;
}

.object-field {
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.nested-form-item:last-child {
  margin-bottom: 0;
}

.routine-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.routine-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.routine-item-info {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.routine-item-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.routine-item-id {
  overflow: hidden;
  font-family: monospace;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-fields {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}

.no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
}
</style>
