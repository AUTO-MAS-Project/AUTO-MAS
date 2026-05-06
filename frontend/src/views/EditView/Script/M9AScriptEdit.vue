<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="../../../assets/M9A.png" alt="M9A" class="breadcrumb-logo" />
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
    <a-card title="M9A脚本配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="cyan" class="type-tag"> M9A </a-tag>
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
                  <a-tooltip title="为脚本设置一个易于识别的名称">
                    <span class="form-label">
                      脚本名称
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input v-model:value="formData.name" placeholder="请输入脚本名称" size="large" class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.name)" />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <a-tooltip title="选择M9A所在的文件夹路径">
                    <span class="form-label">
                      M9A路径
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input v-model:value="formData.path" placeholder="请选择M9A所在的文件夹" size="large" class="path-input"
                    readonly />
                  <a-button size="large" class="path-button" @click="selectM9APath">
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
            <h3>模拟器管理</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="选择要使用的模拟器">
                    <span class="form-label">
                      模拟器
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select v-model:value="m9aConfig.Emulator.Id" size="large" placeholder="请选择模拟器"
                  :loading="emulatorLoading" @change="handleEmulatorSelectChange">
                  <a-select-option v-for="item in emulatorOptions" :key="item.value" :value="item.value">
                    {{ item.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    :title="emulatorDeviceOptions.length === 0 && !emulatorDeviceLoading ? '不支持自动扫描实例的模拟器，请手动输入实例信息' : '选择模拟器的具体实例'">
                    <span class="form-label">
                      模拟器实例
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input v-if="emulatorDeviceOptions.length === 0 && !emulatorDeviceLoading && m9aConfig.Emulator.Id"
                  v-model:value="m9aConfig.Emulator.Index" size="large" placeholder="请输入实例信息，格式：启动附加命令 | ADB地址"
                  class="modern-input" @blur="handleChange('Emulator', 'Index', m9aConfig.Emulator.Index)" />
                <a-select v-else v-model:value="m9aConfig.Emulator.Index" size="large" placeholder="请先选择模拟器"
                  :loading="emulatorDeviceLoading" :disabled="!m9aConfig.Emulator.Id"
                  @change="handleChange('Emulator', 'Index', $event)">
                  <a-select-option v-for="item in emulatorDeviceOptions" :key="item.value" :value="item.value">
                    {{ item.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>运行配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="当用户本日代理成功次数达到该阀值时跳过代理，阈值为「0」时视为无代理次数上限">
                    <span class="form-label">
                      用户单日代理次数上限
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number v-model:value="m9aConfig.Run.ProxyTimesLimit" :min="0" :max="9999" size="large"
                  class="modern-number-input" style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', m9aConfig.Run.ProxyTimesLimit)" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="执行日常代理任务时，M9A日志无变化时间超过该阀值视为超时">
                    <span class="form-label">
                      日常代理超时限制（分钟）
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number v-model:value="m9aConfig.Run.RunTimeLimit" :min="1" :max="9999" size="large"
                  class="modern-number-input" style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', m9aConfig.Run.RunTimeLimit)" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="若重试超过该次数限制仍未完成代理，视为代理失败">
                    <span class="form-label">
                      代理重试次数限制
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number v-model:value="m9aConfig.Run.RunTimesLimit" :min="1" :max="9999" size="large"
                  class="modern-number-input" style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', m9aConfig.Run.RunTimesLimit)" />
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
import type { M9AScriptConfig, ScriptType } from '../../../types/script.ts'
import { useScriptApi } from '../../../composables/useScriptApi.ts'
import { Service, type ComboBoxItem } from '../../../api'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'

const logger = window.electronAPI.getLogger('M9A脚本编辑')

const route = useRoute()
const router = useRouter()
const { getScript, updateScript, loading } = useScriptApi()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true)
const isSaving = ref(false)

const formData = reactive({
  name: '',
  type: 'M9A' as ScriptType,
  get path() {
    return m9aConfig.Info.Path
  },
  set path(value) {
    m9aConfig.Info.Path = value
  },
})

const m9aConfig = reactive<M9AScriptConfig>({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    RunTimeLimit: 30,
  },
  Emulator: {
    Id: '',
    Index: '',
  },
  SubConfigsInfo: {
    UserData: {
      instances: [],
    },
  },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择脚本类型', trigger: 'change' }],
  path: [{ required: true, message: '请选择M9A路径', trigger: 'blur' }],
}

const emulatorLoading = ref(false)
const emulatorDeviceLoading = ref(false)
const emulatorOptions = ref<ComboBoxItem[]>([])
const emulatorDeviceOptions = ref<ComboBoxItem[]>([])

const handleChange = async (category: string, key: string, value: any) => {
  if (isInitializing.value || isSaving.value) return

  isSaving.value = true
  try {
    const updateData: any = { [category]: { [key]: value } }

    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info(`配置已保存: ${category}.${key}`)
      await refreshScript()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const refreshScript = async () => {
  try {
    const scriptDetail = await getScript(scriptId)
    if (scriptDetail) {
      Object.assign(m9aConfig, scriptDetail.config as M9AScriptConfig)
      formData.name = scriptDetail.name
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`刷新配置失败: ${errorMsg}`)
  }
}

onMounted(async () => {
  await loadScript()
  await loadEmulatorOptions()
  isInitializing.value = false
})

const loadScript = async () => {
  pageLoading.value = true
  try {
    const routeState = history.state as any
    if (routeState?.scriptData) {
      const scriptData = routeState.scriptData
      const config = scriptData.config as M9AScriptConfig
      formData.name = config.Info.Name || '新建M9A脚本'
      Object.assign(m9aConfig, config)

      const scriptDetail = await getScript(scriptId)
      if (scriptDetail) {
        formData.type = scriptDetail.type
        formData.name = scriptDetail.name
        Object.assign(m9aConfig, scriptDetail.config as M9AScriptConfig)
      }

      if (m9aConfig.Emulator?.Id) {
        await loadEmulatorDeviceOptions(m9aConfig.Emulator.Id)
      }
    } else {
      const scriptDetail = await getScript(scriptId)

      if (!scriptDetail) {
        message.error('脚本不存在或加载失败')
        router.push('/scripts')
        return
      }

      formData.type = scriptDetail.type
      formData.name = scriptDetail.name

      Object.assign(m9aConfig, scriptDetail.config as M9AScriptConfig)

      if (m9aConfig.Emulator?.Id) {
        await loadEmulatorDeviceOptions(m9aConfig.Emulator.Id)
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

const loadEmulatorOptions = async () => {
  emulatorLoading.value = true
  try {
    const response = await Service.getEmulatorComboxApiInfoComboxEmulatorPost()
    if (response && response.code === 200) {
      emulatorOptions.value = response.data || []
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模拟器选项失败: ${errorMsg}`)
  } finally {
    emulatorLoading.value = false
  }
}

const loadEmulatorDeviceOptions = async (emulatorId: string) => {
  if (!emulatorId) return

  emulatorDeviceLoading.value = true
  try {
    const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
      emulatorId: emulatorId
    })
    if (response && response.code === 200) {
      emulatorDeviceOptions.value = response.data || []
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模拟器实例选项失败: ${errorMsg}`)
  } finally {
    emulatorDeviceLoading.value = false
  }
}

const handleEmulatorSelectChange = async (emulatorId: string) => {
  m9aConfig.Emulator.Index = ''
  emulatorDeviceOptions.value = []

  isSaving.value = true
  try {
    const updateData = {
      Emulator: {
        Id: emulatorId,
        Index: ''
      }
    }
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info('模拟器配置已保存')
      await refreshScript()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存模拟器配置失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }

  if (emulatorId) {
    await loadEmulatorDeviceOptions(emulatorId)
  }
}

const selectM9APath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const path = await (window.electronAPI as any).selectFolder()
    if (path) {
      m9aConfig.Info.Path = path
      await handleChange('Info', 'Path', path)
      message.success('M9A路径选择成功')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择M9A路径失败: ${errorMsg}`)
    message.error('选择文件夹失败')
  }
}
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
  transition: all 0.3s ease;
}

.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.08),
    0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-head-title) {
  font-size: 24px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
  background: var(--ant-color-bg-container);
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
  margin-bottom: 12px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.section-header {
  margin-bottom: 6px;
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
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.modern-select :deep(.ant-select-selector) {
  border: 2px solid var(--ant-color-border) !important;
  border-radius: 8px !important;
  background: var(--ant-color-bg-container) !important;
  transition: all 0.3s ease;
}

.modern-select:hover :deep(.ant-select-selector) {
  border-color: var(--ant-color-primary-hover) !important;
}

.modern-select.ant-select-focused :deep(.ant-select-selector) {
  border-color: var(--ant-color-primary) !important;
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1) !important;
}

.modern-number-input {
  border-radius: 8px;
}

.modern-number-input :deep(.ant-input-number) {
  border: 2px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-number-input :deep(.ant-input-number:hover) {
  border-color: var(--ant-color-primary-hover);
}

.modern-number-input :deep(.ant-input-number-focused) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
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
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
  background: var(--ant-color-bg-container) !important;
}

.path-input:focus {
  box-shadow: none !important;
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

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

.config-form :deep(.ant-form-item-label) {
  padding-bottom: 8px;
}

.config-form :deep(.ant-form-item-label > label) {
  font-weight: 600;
  color: var(--ant-color-text);
}

@media (prefers-color-scheme: dark) {
  .config-card {
    box-shadow:
      0 4px 20px rgba(0, 0, 0, 0.3),
      0 1px 3px rgba(0, 0, 0, 0.4);
  }

  .path-input-group:focus-within {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }

  .modern-input:focus,
  .modern-input.ant-input-focused {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }

  .modern-select.ant-select-focused :deep(.ant-select-selector) {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2) !important;
  }

  .modern-number-input :deep(.ant-input-number-focused) {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }
}

@media (max-width: 1200px) {
  .config-card :deep(.ant-card-body) {
    padding: 24px;
  }

  .form-section {
    margin-bottom: 12px;
  }
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-head) {
    padding: 16px 20px;
  }

  .config-card :deep(.ant-card-head-title) {
    font-size: 20px;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }

  .section-header h3 {
    font-size: 18px;
  }

  .form-section {
    margin-bottom: 12px;
  }

  .path-button {
    padding: 0 16px;
    font-size: 14px;
  }

  .cancel-button,
  .save-button {
    height: 44px;
    font-size: 14px;
    padding: 0 20px;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.form-section {
  animation: fadeInUp 0.6s ease-out;
}

.form-section:nth-child(2) {
  animation-delay: 0.1s;
}

.form-section:nth-child(3) {
  animation-delay: 0.2s;
}

:deep(.ant-tooltip-inner) {
  background: var(--ant-color-bg-elevated);
  color: var(--ant-color-text);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.5;
  max-width: 300px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

:deep(.ant-tooltip-arrow::before) {
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border);
}

.float-button {
  width: 60px;
  height: 60px;
}
</style>
