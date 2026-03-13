<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="../../../assets/MAA.png" alt="MaaEnd" class="breadcrumb-logo" />
            编辑脚本
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
    <a-card title="MaaEnd 脚本配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="orange" class="type-tag">MaaEnd</a-tag>
      </template>

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>基本信息</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    脚本名称
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  placeholder="请输入脚本名称"
                  size="large"
                  class="modern-input"
                  @blur="handleNameBlur"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <span class="form-label">
                    MaaEnd 路径
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    placeholder="请选择 MaaEnd 所在目录"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectMaaEndPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件夹
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>运行配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    控制器类型
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </template>
                <a-select
                  v-model:value="config.Run.ControllerType"
                  size="large"
                  @change="handleChange('Run', 'ControllerType', $event)"
                >
                  <a-select-option value="Win32">Win32</a-select-option>
                  <a-select-option value="ADB">ADB</a-select-option>
                  <a-select-option value="PlayCover">PlayCover</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">超时（分钟）</span>
                </template>
                <a-input-number
                  v-model:value="config.Run.Timeout"
                  :min="0"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'Timeout', config.Run.Timeout)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">重试次数</span>
                </template>
                <a-input-number
                  v-model:value="config.Run.Retry"
                  :min="0"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'Retry', config.Run.Retry)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">运行次数限制</span>
                </template>
                <a-input-number
                  v-model:value="config.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', config.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>MaaEnd 配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">资源配置</span>
                </template>
                <a-input
                  v-model:value="config.MaaEnd.ResourceProfile"
                  placeholder="例如：MaaEnd"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('MaaEnd', 'ResourceProfile', config.MaaEnd.ResourceProfile)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">预设任务</span>
                </template>
                <a-select
                  v-if="presetOptions.length > 0"
                  v-model:value="config.MaaEnd.PresetTask"
                  size="large"
                  show-search
                  allow-clear
                  placeholder="请选择预设任务"
                  :options="presetOptions"
                  @change="handleChange('MaaEnd', 'PresetTask', $event || '')"
                />
                <a-input
                  v-else
                  v-model:value="config.MaaEnd.PresetTask"
                  placeholder="请输入预设任务"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('MaaEnd', 'PresetTask', config.MaaEnd.PresetTask)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">日志路径</span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="config.MaaEnd.LogPath"
                    placeholder="请选择日志文件"
                    size="large"
                    class="path-input"
                    @blur="handleChange('MaaEnd', 'LogPath', config.MaaEnd.LogPath)"
                  />
                  <a-button size="large" class="path-button" @click="selectLogPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { ScriptType } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'

const logger = window.electronAPI.getLogger('MaaEnd脚本编辑')

interface MaaEndScriptConfigLocal {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    Timeout: number
    Retry: number
    RunTimesLimit: number
    ControllerType: 'Win32' | 'ADB' | 'PlayCover'
  }
  MaaEnd: {
    ResourceProfile: string
    PresetTask: string
    LogPath: string
    SuccessPattern: string
    ErrorPattern: string
  }
}

const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const isInitializing = ref(true)
const isSaving = ref(false)
const presetOptions = ref<Array<{ label: string; value: string }>>([])

const scriptId = route.params.id as string

const config = reactive<MaaEndScriptConfigLocal>({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    Timeout: 10,
    Retry: 3,
    RunTimesLimit: 3,
    ControllerType: 'Win32',
  },
  MaaEnd: {
    ResourceProfile: 'MaaEnd',
    PresetTask: '',
    LogPath: '',
    SuccessPattern: '',
    ErrorPattern: '',
  },
})

const formData = reactive({
  name: '',
  type: 'MaaEnd' as ScriptType,
  get path() {
    return config.Info.Path
  },
  set path(value: string) {
    config.Info.Path = value
  },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  path: [{ required: true, message: '请选择 MaaEnd 路径', trigger: 'blur' }],
}

const applyConfig = (rawConfig: any, nameFallback = '新建MaaEnd脚本') => {
  config.Info.Name = rawConfig?.Info?.Name ?? nameFallback
  config.Info.Path = rawConfig?.Info?.Path ?? '.'

  config.Run.Timeout = rawConfig?.Run?.Timeout ?? 10
  config.Run.Retry = rawConfig?.Run?.Retry ?? 3
  config.Run.RunTimesLimit = rawConfig?.Run?.RunTimesLimit ?? 3
  config.Run.ControllerType = rawConfig?.Run?.ControllerType ?? 'Win32'

  config.MaaEnd.ResourceProfile = rawConfig?.MaaEnd?.ResourceProfile ?? 'MaaEnd'
  config.MaaEnd.PresetTask = rawConfig?.MaaEnd?.PresetTask ?? ''
  config.MaaEnd.LogPath = rawConfig?.MaaEnd?.LogPath ?? ''
  config.MaaEnd.SuccessPattern = rawConfig?.MaaEnd?.SuccessPattern ?? ''
  config.MaaEnd.ErrorPattern = rawConfig?.MaaEnd?.ErrorPattern ?? ''

  formData.name = config.Info.Name
}

const refreshScript = async () => {
  const scriptDetail = await getScript(scriptId)
  if (!scriptDetail) {
    return
  }
  if (scriptDetail.type !== 'MaaEnd') {
    message.error('脚本类型不匹配')
    router.push('/scripts')
    return
  }
  formData.type = scriptDetail.type
  applyConfig(scriptDetail.config, scriptDetail.name || '新建MaaEnd脚本')
}

const handleChange = async (category: string, key: string, value: any) => {
  if (isInitializing.value || isSaving.value) {
    return
  }

  isSaving.value = true
  try {
    const updateData: Record<string, any> = {
      [category]: {
        [key]: value,
      },
    }
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info(`配置已保存: ${category}.${key}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const handleNameBlur = async () => {
  config.Info.Name = formData.name
  await handleChange('Info', 'Name', formData.name)
}

const resolveMaaEndConfigPath = () => {
  const base = String(config.Info.Path || '').trim()
  if (!base) {
    return ''
  }
  return `${base.replace(/[\\/]+$/, '')}/config/mxu-MaaEnd.json`
}

const loadPresetOptions = async () => {
  const configPath = resolveMaaEndConfigPath()
  if (!configPath || !window.electronAPI?.readFile) {
    presetOptions.value = []
    return
  }

  try {
    const content = await window.electronAPI.readFile(configPath)
    const parsed = JSON.parse(content)
    const instances = Array.isArray(parsed?.instances) ? parsed.instances : []

    const names = Array.from(
      new Set(
        instances
          .map((item: any) => String(item?.name || '').trim())
          .filter((name: string) => name.length > 0)
      )
    )

    presetOptions.value = names.map(name => ({
      label: name,
      value: name,
    }))
  } catch (error) {
    presetOptions.value = []
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`加载 MaaEnd 预设任务选项失败: ${errorMsg}`)
  }
}
const loadScript = async () => {
  pageLoading.value = true
  try {
    const routeState = history.state as any
    if (routeState?.scriptData?.config) {
      applyConfig(routeState.scriptData.config)
      await refreshScript()
      return
    }

    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) {
      message.error('脚本不存在或加载失败')
      router.push('/scripts')
      return
    }
    if (scriptDetail.type !== 'MaaEnd') {
      message.error('脚本类型不匹配')
      router.push('/scripts')
      return
    }

    formData.type = scriptDetail.type
    applyConfig(scriptDetail.config, scriptDetail.name || '新建MaaEnd脚本')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
  }
}

const selectMaaEndPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const path = await (window.electronAPI as any).selectFolder()
    if (!path) {
      return
    }

    config.Info.Path = path
    formData.path = path
    await handleChange('Info', 'Path', path)
    await loadPresetOptions()
    message.success('MaaEnd 路径选择成功')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择 MaaEnd 路径失败: ${errorMsg}`)
    message.error('选择文件夹失败')
  }
}

const selectLogPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const selected = await (window.electronAPI as any).selectFile()
    const path = Array.isArray(selected) ? selected[0] : selected
    if (!path) {
      return
    }

    config.MaaEnd.LogPath = path
    await handleChange('MaaEnd', 'LogPath', path)
    message.success('日志路径选择成功')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择日志路径失败: ${errorMsg}`)
    message.error('选择日志路径失败')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(async () => {
  await loadScript()
  await loadPresetOptions()
  isInitializing.value = false
})
</script>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 0 8px;
}

.breadcrumb-link {
  color: var(--ant-color-text-secondary);
  text-decoration: none;
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

.config-card {
  border-radius: 12px;
}

.form-section {
  margin-bottom: 24px;
}

.section-header h3 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.help-icon {
  color: var(--ant-color-text-description);
}

.path-input-group {
  display: flex;
}

.path-input {
  flex: 1;
}

.path-button {
  min-width: 110px;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
