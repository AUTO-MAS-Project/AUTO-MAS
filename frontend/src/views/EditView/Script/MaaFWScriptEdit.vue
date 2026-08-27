<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="../../../assets/AUTO-MAS.ico" alt="MaaFW" class="breadcrumb-logo" />
            编辑 MaaFW 脚本
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card title="MaaFW 脚本配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="geekblue" class="type-tag"> MaaFW（外部运行）</a-tag>
      </template>

      <a-form layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header"><h3>基本信息</h3></div>
          <a-row :gutter="24">
            <a-col :xs="24" :lg="8">
              <a-form-item label="脚本名称">
                <a-input
                  v-model:value="maafwConfig.Info.Name"
                  placeholder="请输入脚本名称"
                  size="large"
                  @blur="handleChange('Info', 'Name', maafwConfig.Info.Name)"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="16">
              <a-form-item label="MaaFW 项目目录（需包含 interface.json）">
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="maafwConfig.Info.Path"
                    placeholder="请选择 MaaFW 项目根目录"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectProjectPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件夹
                  </a-button>
                  <a-button
                    v-if="maafwConfig.Info.Path"
                    size="large"
                    class="path-button path-refresh-button"
                    :loading="previewLoading"
                    @click="runPreview"
                  >
                    重新读取
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>

          <a-alert
            v-if="previewError"
            type="error"
            show-icon
            :message="previewError"
            style="margin-top: 4px"
          />
          <a-alert
            v-else-if="previewProject"
            type="success"
            show-icon
            :message="`已读取项目 ${previewProject}：控制器 ${controllerOptions.length} · 资源 ${resourceOptions.length} · 可选任务 ${taskOptions.length}`"
            style="margin-top: 4px"
          />
        </div>

        <!-- 运行选择 -->
        <div class="form-section">
          <div class="section-header"><h3>运行选择</h3></div>
          <a-spin :spinning="previewLoading">
            <a-row :gutter="24">
              <a-col :xs="24" :lg="12">
                <a-form-item label="控制器（单选）">
                  <a-select
                    v-model:value="selectedController"
                    size="large"
                    placeholder="请先读取项目目录再选择控制器"
                    :disabled="!controllerOptions.length"
                    allow-clear
                    @change="handleControllerChange"
                  >
                    <a-select-option
                      v-for="item in controllerOptions"
                      :key="item.name"
                      :value="item.name"
                    >
                      {{ item.label || item.name }}（{{ item.type }}）
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :xs="24" :lg="12">
                <a-form-item label="资源（单选）">
                  <a-select
                    v-model:value="selectedResource"
                    size="large"
                    placeholder="请先读取项目目录再选择资源"
                    :disabled="!resourceOptions.length"
                    allow-clear
                    @change="handleResourceChange"
                  >
                    <a-select-option
                      v-for="item in resourceOptions"
                      :key="item.name"
                      :value="item.name"
                    >
                      {{ item.label || item.name }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24">
              <a-col :span="24">
                <a-form-item label="任务（多选，按选中顺序执行）">
                  <a-select
                    v-model:value="selectedTasks"
                    mode="multiple"
                    size="large"
                    placeholder="请选择要执行的任务"
                    :disabled="!taskOptions.length"
                    option-filter-prop="label"
                    @change="handleTasksChange"
                  >
                    <a-select-option
                      v-for="item in taskOptions"
                      :key="item.name"
                      :value="item.name"
                      :label="item.label || item.name"
                    >
                      {{ item.label || item.name }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
                <a-alert
                  v-if="previewProject && !selectedTasks.length"
                  type="warning"
                  show-icon
                  message="尚未选择任何任务，MaaFW 运行时会被后端拒绝启动。"
                  style="margin-top: -12px"
                />
              </a-col>
            </a-row>
          </a-spin>
        </div>

        <!-- 运行配置 -->
        <div class="form-section">
          <div class="section-header"><h3>运行配置</h3></div>
          <a-row :gutter="24">
            <a-col :xs="24" :lg="8">
              <a-form-item label="单次运行时间限制">
                <a-input-number
                  v-model:value="maafwConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  addon-after="分钟"
                  size="large"
                  style="width: 100%"
                  @change="handleRunTimeLimitChange"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-typography-text type="secondary">
            运行引擎：外部运行（MFAAvalonia
            外壳）。设备标识需先在外壳侧连接一次模拟器后由项目自带配置提供，MAS 暂不写入设备字段。
          </a-typography-text>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import type { MaaFWControllerInfo, MaaFWResourceInfo, MaaFWTaskInfo } from '@/api'
import type { MaaFWScriptConfig } from '@/types/script'

const logger = window.electronAPI.getLogger('MaaFW 脚本编辑')

// MaaFW pretask 伪任务：预览接口会把它们混进 tasks[]（entry 固定为 MXU_PRETASK、
// name 带 __MXU_PRETASK__ 前缀），而后端 _parse_task_selection 用 is_pretask_task_name
// 明确拒绝，绝不能让用户选到。此处按 entry 过滤、name 前缀兜底。
const PRETASK_TASK_ENTRY = 'MXU_PRETASK'
const PRETASK_TASK_PREFIX = '__MXU_PRETASK__'
const isPretaskTask = (task: MaaFWTaskInfo): boolean =>
  task.entry === PRETASK_TASK_ENTRY || task.name.startsWith(PRETASK_TASK_PREFIX)

const route = useRoute()
const router = useRouter()
const { getScript, updateScript, previewMaaFWInterface } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(false)
const isInitializing = ref(true)
const isSaving = ref(false)

const previewLoading = ref(false)
const previewError = ref('')
const previewProject = ref('')

const controllerOptions = ref<MaaFWControllerInfo[]>([])
const resourceOptions = ref<MaaFWResourceInfo[]>([])
const taskOptions = ref<MaaFWTaskInfo[]>([])

const selectedController = ref<string | undefined>(undefined)
const selectedResource = ref<string | undefined>(undefined)
const selectedTasks = ref<string[]>([])

const maafwConfig = reactive({
  Info: { Name: '', Path: '' },
  Run: { Engine: 'external', RunTimeLimit: 30 },
})

// ConfigBase 把 Selection 三个列表以 JSON 字符串保存、读回也是字符串；
// 兼容后端某天直接返回数组的情况，统一收敛成字符串数组。
const parseSelectionList = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === 'string')
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value)
      return Array.isArray(parsed)
        ? parsed.filter((item): item is string => typeof item === 'string')
        : []
    } catch {
      return []
    }
  }
  return []
}

const saveSelection = async (key: 'Controller' | 'Resource' | 'Tasks', list: string[]) => {
  if (isInitializing.value) return
  isSaving.value = true
  try {
    // 后端 JSONValidator(list) 只接受 JSON 字符串，裸数组会被清空成 "[ ]"
    const success = await updateScript(scriptId, { Selection: { [key]: JSON.stringify(list) } })
    if (success) logger.info(`配置已保存: Selection.${key}`)
  } catch (error) {
    logger.error(`保存失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    isSaving.value = false
  }
}

const handleChange = async (category: 'Info' | 'Run', key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const success = await updateScript(scriptId, { [category]: { [key]: value } })
    if (success) logger.info(`配置已保存: ${category}.${key}`)
  } catch (error) {
    logger.error(`保存失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    isSaving.value = false
  }
}

const handleRunTimeLimitChange = (value: number | string | null) => {
  const normalized = typeof value === 'number' && value >= 1 ? Math.floor(value) : 30
  maafwConfig.Run.RunTimeLimit = normalized
  void handleChange('Run', 'RunTimeLimit', normalized)
}

const handleControllerChange = (value: string | undefined) => {
  selectedController.value = value || undefined
  void saveSelection('Controller', value ? [value] : [])
}

const handleResourceChange = (value: string | undefined) => {
  selectedResource.value = value || undefined
  void saveSelection('Resource', value ? [value] : [])
}

const handleTasksChange = (value: string[]) => {
  selectedTasks.value = value
  void saveSelection('Tasks', value)
}

const clearPreviewOptions = () => {
  previewProject.value = ''
  controllerOptions.value = []
  resourceOptions.value = []
  taskOptions.value = []
}

const runPreview = async () => {
  const path = maafwConfig.Info.Path.trim()
  if (!path) {
    previewError.value = ''
    clearPreviewOptions()
    return
  }
  previewLoading.value = true
  previewError.value = ''
  try {
    const response = await previewMaaFWInterface(path)
    if (!response) {
      previewError.value = '预览 MaaFW interface 失败，请检查后端服务与项目目录'
      clearPreviewOptions()
      return
    }
    if (response.code !== 200 || !response.data) {
      // 后端 message 原样呈现：目录缺 interface.json、解析失败等都在这里
      previewError.value = response.message || 'MaaFW interface 预览失败'
      clearPreviewOptions()
      return
    }
    const data = response.data
    controllerOptions.value = data.controllers ?? []
    resourceOptions.value = data.resources ?? []
    taskOptions.value = (data.tasks ?? []).filter(task => !isPretaskTask(task))
    previewProject.value = data.project?.label || data.project?.name || path

    // 预览结果变化后，剔除已不存在的历史选择，避免提交后端未定义项
    const controllerNames = new Set(controllerOptions.value.map(item => item.name))
    const resourceNames = new Set(resourceOptions.value.map(item => item.name))
    const taskNames = new Set(taskOptions.value.map(item => item.name))
    if (selectedController.value && !controllerNames.has(selectedController.value)) {
      selectedController.value = undefined
    }
    if (selectedResource.value && !resourceNames.has(selectedResource.value)) {
      selectedResource.value = undefined
    }
    selectedTasks.value = selectedTasks.value.filter(name => taskNames.has(name))
  } catch (error) {
    previewError.value = error instanceof Error ? error.message : String(error)
    clearPreviewOptions()
  } finally {
    previewLoading.value = false
  }
}

const selectProjectPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }
    const path = await window.electronAPI.selectFolder()
    if (!path) return
    maafwConfig.Info.Path = path
    await handleChange('Info', 'Path', path)
    await runPreview()
  } catch (error) {
    logger.error(`选择项目目录失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error('选择文件夹失败')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(async () => {
  pageLoading.value = true
  try {
    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) {
      message.error('脚本不存在或加载失败')
      router.push('/scripts')
      return
    }
    const config = scriptDetail.config as MaaFWScriptConfig
    maafwConfig.Info.Name = config.Info?.Name ?? scriptDetail.name ?? '新 MaaFW 脚本'
    maafwConfig.Info.Path = config.Info?.Path ?? ''
    maafwConfig.Run.Engine = config.Run?.Engine ?? 'external'
    maafwConfig.Run.RunTimeLimit = config.Run?.RunTimeLimit ?? 30
    selectedController.value = parseSelectionList(config.Selection?.Controller)[0]
    selectedResource.value = parseSelectionList(config.Selection?.Resource)[0]
    selectedTasks.value = parseSelectionList(config.Selection?.Tasks)

    if (maafwConfig.Info.Path) {
      await runPreview()
    }
  } catch (error) {
    logger.error(`加载脚本失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
    isInitializing.value = false
  }
})
</script>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.breadcrumb-link {
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
  transition: color 0.3s ease;
}

.breadcrumb-current {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow: none;
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
}

.config-form {
  max-width: none;
}

.form-section {
  margin-bottom: 20px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.section-header {
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
  transition: all 0.3s ease;
}

.path-input-group:hover {
  border-color: var(--ant-color-primary-hover);
}

.path-input-group:focus-within {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px var(--ant-color-primary-bg);
}

.path-input-group :deep(.path-input.ant-input) {
  flex: 1;
  border: none;
  border-radius: 0;
  background: var(--ant-color-bg-container);
}

.path-input-group :deep(.path-input.ant-input:focus) {
  box-shadow: none;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  transition: all 0.3s ease;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.path-button:hover {
  background: var(--ant-color-primary);
  color: white;
  transform: none;
}

.cancel-button {
  height: 40px;
}
</style>
