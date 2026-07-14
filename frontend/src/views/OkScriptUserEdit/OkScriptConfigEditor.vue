<template>
  <div class="ok-script-config-editor">
    <div class="editor-header">
      <h3>{{ title }}</h3>
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
              <div class="form-title">
                <h4>{{ selectedConfigForTemplate.displayName }}</h4>
                <span class="form-filename">{{ selectedConfigForTemplate.filename }}</span>
              </div>
              <label v-if="sectionOptions.length > 1" class="section-selector">
                <span>配置选择</span>
                <a-select v-model:value="currentSection" size="middle">
                  <a-select-option
                    v-for="section in sectionOptions"
                    :key="section.value"
                    :value="section.value"
                  >
                    {{ section.label }}
                  </a-select-option>
                </a-select>
              </label>
            </div>

            <a-form layout="vertical" class="form-fields">
              <a-form-item
                v-for="field in selectedFields"
                :key="field.name"
                :label="field.label || field.name"
              >
                <template v-if="field.description" #extra>
                  {{ field.description }}
                </template>

                <!-- bool 类型：开关 -->
                <a-switch
                  v-if="field.type === 'bool'"
                  :checked="
                    getFieldValue(selectedConfigForTemplate.filename, field.name, field.value)
                  "
                  @change="
                    (val: boolean) =>
                      setFieldValue(selectedConfigForTemplate.filename, field.name, val)
                  "
                />

                <!-- select 类型：下拉选择 -->
                <a-select
                  v-else-if="field.type === 'select'"
                  :value="
                    getFieldValue(selectedConfigForTemplate.filename, field.name, field.value)
                  "
                  style="width: 100%"
                  @change="
                    (val: string) =>
                      setFieldValue(selectedConfigForTemplate.filename, field.name, val)
                  "
                >
                  <a-select-option
                    v-for="opt in getFieldOptions(selectedConfigForTemplate.filename, field)"
                    :key="opt"
                    :value="opt"
                  >
                    {{ getOptionLabel(opt) }}
                  </a-select-option>
                </a-select>

                <!-- list 类型：多选 -->
                <a-select
                  v-else-if="field.type === 'list'"
                  :value="
                    getFieldValue(selectedConfigForTemplate.filename, field.name, field.value)
                  "
                  :mode="getListSelectMode(field)"
                  style="width: 100%"
                  placeholder="请选择或输入后回车"
                  @change="
                    (val: string[]) =>
                      setFieldValue(selectedConfigForTemplate.filename, field.name, val)
                  "
                >
                  <a-select-option
                    v-for="opt in getFieldOptions(selectedConfigForTemplate.filename, field)"
                    :key="opt"
                    :value="opt"
                  >
                    {{ getOptionLabel(opt) }}
                  </a-select-option>
                </a-select>

                <!-- int 类型：整数输入 -->
                <a-input-number
                  v-else-if="field.type === 'int'"
                  :value="
                    getFieldValue(selectedConfigForTemplate.filename, field.name, field.value)
                  "
                  :min="field.min"
                  :max="field.max"
                  style="width: 100%"
                  @change="
                    (val: number | null) => {
                      if (val !== null)
                        setFieldValue(selectedConfigForTemplate.filename, field.name, val)
                    }
                  "
                />

                <!-- float 类型：浮点数输入 -->
                <a-input-number
                  v-else-if="field.type === 'float'"
                  :value="
                    getFieldValue(selectedConfigForTemplate.filename, field.name, field.value)
                  "
                  :min="field.min"
                  :max="field.max"
                  :step="field.step || 0.1"
                  style="width: 100%"
                  @change="
                    (val: number | null) => {
                      if (val !== null)
                        setFieldValue(selectedConfigForTemplate.filename, field.name, val)
                    }
                  "
                />

                <!-- hotkey 类型：快捷键输入 -->
                <a-input
                  v-else-if="field.type === 'hotkey'"
                  :value="
                    getFieldValue(selectedConfigForTemplate.filename, field.name, field.value)
                  "
                  style="width: 100%"
                  @change="
                    (e: Event) =>
                      setFieldValue(
                        selectedConfigForTemplate.filename,
                        field.name,
                        (e.target as HTMLInputElement).value
                      )
                  "
                />

                <!-- textarea 类型：多行文本配置 -->
                <a-textarea
                  v-else-if="field.type === 'textarea'"
                  :value="
                    String(
                      getFieldValue(selectedConfigForTemplate.filename, field.name, field.value) ||
                        ''
                    )
                  "
                  :rows="5"
                  :placeholder="field.name === '账号列表' ? '每行一个账号' : '请输入内容'"
                  @change="
                    (e: Event) =>
                      setFieldValue(
                        selectedConfigForTemplate.filename,
                        field.name,
                        (e.target as HTMLTextAreaElement).value
                      )
                  "
                />

                <!-- json 类型：未知项目的嵌套配置保留对象结构 -->
                <a-textarea
                  v-else-if="field.type === 'json'"
                  :value="
                    formatJsonValue(
                      getFieldValue(selectedConfigForTemplate.filename, field.name, field.value)
                    )
                  "
                  :rows="8"
                  placeholder="请输入 JSON 对象或数组"
                  @change="
                    (e: Event) =>
                      setJsonFieldValue(
                        selectedConfigForTemplate.filename,
                        field.name,
                        (e.target as HTMLTextAreaElement).value
                      )
                  "
                />

                <!-- string 类型：文本输入 -->
                <a-input
                  v-else
                  :value="
                    getFieldValue(selectedConfigForTemplate.filename, field.name, field.value)
                  "
                  style="width: 100%"
                  @change="
                    (e: Event) =>
                      setFieldValue(
                        selectedConfigForTemplate.filename,
                        field.name,
                        (e.target as HTMLInputElement).value
                      )
                  "
                />
              </a-form-item>

              <div v-if="selectedFields.length === 0" class="empty-fields">
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
import {
  useOkScriptConfigApi,
  type OkScriptConfigFile as ConfigFile,
  type OkScriptConfigPatchMap,
} from '@/composables/useOkScriptConfigApi'

type ConfigField = ConfigFile['fields'][number]

const props = withDefaults(
  defineProps<{
    scriptId: string
    userId: string
    endpointPrefix?: string
    title?: string
  }>(),
  {
    endpointPrefix: '/plugin/ok-script/configs',
    title: '配置编辑',
  }
)

const emit = defineEmits<{
  saved: []
}>()

const logger = window.electronAPI.getLogger('ok-script配置编辑')

const loading = ref(false)
const configs = ref<ConfigFile[]>([])
const selectedFilename = ref<string | null>(null)
const changedFiles = ref(new Set<string>())
const localChanges = ref<Record<string, Record<string, any>>>({})
const optionLabels = ref<Record<string, string>>({})
const selectedSections = ref<Record<string, string>>({})

const emptyConfig: ConfigFile = {
  filename: '',
  displayName: '',
  group: '',
  taskIndex: null,
  fieldCount: 0,
  fields: [],
  currentData: {},
}

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

const selectedConfigForTemplate = computed<ConfigFile>(() => selectedConfig.value || emptyConfig)
const hasChanges = computed(() => changedFiles.value.size > 0)
const okScriptConfigApi = useOkScriptConfigApi(props.endpointPrefix)

const getFieldSection = (field: ConfigField) => field.section || '全部配置'

const getSectionOptions = (config: ConfigFile | null) => {
  if (!config) return []

  const sections = new Map<string, number>()
  for (const field of config.fields) {
    const section = getFieldSection(field)
    const priority = field.sectionPriority ?? field.priority ?? Number.MAX_SAFE_INTEGER
    const currentPriority = sections.get(section)
    if (currentPriority === undefined || priority < currentPriority) {
      sections.set(section, priority)
    }
  }

  return [...sections.entries()]
    .sort(([leftSection, leftPriority], [rightSection, rightPriority]) => {
      if (leftPriority !== rightPriority) return leftPriority - rightPriority
      return leftSection.localeCompare(rightSection, 'zh-CN')
    })
    .map(([section]) => ({ label: section, value: section }))
}

const sectionOptions = computed(() => getSectionOptions(selectedConfig.value))

const currentSection = computed({
  get: () => {
    const config = selectedConfig.value
    if (!config) return ''
    return selectedSections.value[config.filename] || sectionOptions.value[0]?.value || ''
  },
  set: (section: string) => {
    const config = selectedConfig.value
    if (config) {
      selectedSections.value[config.filename] = section
    }
  },
})

const selectedFields = computed(() => {
  const section = currentSection.value
  return [...selectedConfigForTemplate.value.fields]
    .filter(field => !section || getFieldSection(field) === section)
    .sort((left, right) => {
      const leftPriority = left.priority ?? Number.MAX_SAFE_INTEGER
      const rightPriority = right.priority ?? Number.MAX_SAFE_INTEGER
      if (leftPriority !== rightPriority) return leftPriority - rightPriority
      return (left.label || left.name).localeCompare(right.label || right.name, 'zh-CN')
    })
})

const getOptionLabel = (value: string) => {
  return optionLabels.value[value] || value
}

const getFieldValue = (filename: string, fieldName: string, fallback: any) => {
  if (localChanges.value[filename] && localChanges.value[filename][fieldName] !== undefined) {
    return localChanges.value[filename][fieldName]
  }
  return fallback
}

const getFieldOptions = (filename: string, field: ConfigFile['fields'][number]) => {
  const options = Array.isArray(field.options) ? [...field.options] : []
  const value = getFieldValue(filename, field.name, field.value)
  const values = Array.isArray(value) ? value : [value]

  for (const item of values) {
    if (item === null || item === undefined) continue
    const text = String(item)
    if (text && !options.includes(text)) {
      options.push(text)
    }
  }

  return options
}

const getListSelectMode = (field: ConfigFile['fields'][number]) => {
  return Array.isArray(field.options) && field.options.length > 0 ? 'multiple' : 'tags'
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
    if (Object.keys(localChanges.value[filename]).length === 0) {
      delete localChanges.value[filename]
      changedFiles.value.delete(filename)
    }
  } else {
    localChanges.value[filename][fieldName] = value
    changedFiles.value.add(filename)
  }
  // 触发响应式更新
  changedFiles.value = new Set(changedFiles.value)
}

const formatJsonValue = (value: unknown) => JSON.stringify(value, null, 2) || ''

const setJsonFieldValue = (filename: string, fieldName: string, text: string) => {
  try {
    setFieldValue(filename, fieldName, JSON.parse(text))
  } catch {
    message.warning('JSON 格式无效，未保存本次修改')
  }
}

const selectConfig = (filename: string) => {
  selectedFilename.value = filename
  const config = configs.value.find(item => item.filename === filename) || null
  const sections = getSectionOptions(config)
  if (
    sections.length > 0 &&
    !sections.some(section => section.value === selectedSections.value[filename])
  ) {
    selectedSections.value[filename] = sections[0].value
  }
}

const loadConfigs = async () => {
  if (!props.scriptId || !props.userId) return
  loading.value = true
  try {
    const resp = await okScriptConfigApi.listConfigFiles(props.scriptId, props.userId)
    if (resp?.code === 200 && resp?.data) {
      configs.value = resp.data
      optionLabels.value = resp.optionLabels || {}
      if (
        selectedFilename.value &&
        !configs.value.some(config => config.filename === selectedFilename.value)
      ) {
        selectedFilename.value = null
      }
      if (configs.value.length > 0 && !selectedFilename.value) {
        selectConfig(configs.value[0].filename)
      } else if (selectedFilename.value) {
        selectConfig(selectedFilename.value)
      }
    } else {
      message.error(resp?.message || '加载配置失败')
    }
  } catch (e) {
    logger.error(`加载配置失败: ${e instanceof Error ? e.message : String(e)}`)
    message.error('加载配置失败')
  } finally {
    loading.value = false
  }
}

const saveAll = async (silent = true) => {
  if (!hasChanges.value) return
  try {
    const configsToUpdate: OkScriptConfigPatchMap = { ...localChanges.value }
    const resp = await okScriptConfigApi.batchUpdateConfigFiles(
      props.scriptId,
      props.userId,
      configsToUpdate
    )
    if (resp?.code === 200) {
      // 更新本地数据
      for (const [filename, data] of Object.entries(configsToUpdate)) {
        const config = configs.value.find(c => c.filename === filename)
        if (config) {
          Object.assign(config.currentData, data)
          for (const field of config.fields) {
            if (data[field.name] !== undefined) {
              field.value = data[field.name]
            }
          }
        }
      }
      changedFiles.value = new Set()
      localChanges.value = {}
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
  () => [props.scriptId, props.userId],
  async () => {
    if (props.scriptId && props.userId) {
      if (hasChanges.value) {
        await saveAll(true)
      }
      selectedFilename.value = null
      changedFiles.value = new Set()
      localChanges.value = {}
      selectedSections.value = {}
      await loadConfigs()
    }
  }
)
</script>

<style scoped>
.ok-script-config-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: min(720px, calc(100vh - 260px));
  min-height: 520px;
}

.ok-script-config-editor :deep(.ant-spin-nested-loading),
.ok-script-config-editor :deep(.ant-spin-container) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.editor-header {
  display: flex;
  flex-shrink: 0;
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
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.editor-layout {
  flex: 1;
  min-height: 0;
}

.left-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  border-right: 1px solid var(--ant-color-border);
  padding-right: 24px;
  overflow: hidden;
}

.config-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  padding-right: 4px;
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
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding-left: 24px;
  overflow: hidden;
}

.config-form {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 20px;
  min-height: 0;
  overflow: hidden;
}

.form-header {
  display: flex;
  flex-shrink: 0;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.form-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.form-header h4 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.form-filename {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  font-family: monospace;
}

.section-selector {
  display: flex;
  flex: 0 0 260px;
  flex-direction: column;
  gap: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.form-fields {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.form-fields :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.form-fields :deep(.ant-form-item-label) {
  font-weight: 600;
}

.empty-fields {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}

.no-selection {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  min-height: 0;
}

@media (max-width: 768px) {
  .ok-script-config-editor {
    height: calc(100vh - 180px);
    min-height: 480px;
  }

  .form-header {
    align-items: stretch;
    flex-direction: column;
  }

  .section-selector {
    flex-basis: auto;
  }
}
</style>
