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
        <a-tag color="geekblue" class="type-tag">MAAEND</a-tag>
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
          <a-row :gutter="24">
            <a-col v-if="config.Run.ControllerType !== 'ADB'" :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">Endfield 路径（Win32）</span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="config.Run.GamePath"
                    placeholder="请选择 Endfield.exe"
                    size="large"
                    class="path-input"
                    @blur="handleChange('Run', 'GamePath', config.Run.GamePath)"
                  />
                  <a-button size="large" class="path-button" @click="selectGamePath">
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

        <div class="form-section">
          <div class="section-header">
            <h3>运行配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
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
                  <a-select-option value="Win32-Window">电脑端-默认</a-select-option>
                  <a-select-option value="Win32-Window-Background">电脑端-后台</a-select-option>
                  <a-select-option value="Win32-Front">电脑端-前台</a-select-option>
                  <a-select-option value="ADB">安卓端</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
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
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="当用户本日代理成功次数达到该阀值时跳过代理，阈值为「0」时视为无代理次数上限">
                    <span class="form-label">
                      用户单日代理次数上限
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="config.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', config.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="若重试超过该次数限制仍未完成代理，视为代理失败">
                    <span class="form-label">
                      代理重试次数限制
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
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
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="开启后在执行多用户流程时进入切号逻辑">
                    <span class="form-label">
                      启用切号
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-switch
                  :checked="config.Run.IfAccountSwitch"
                  checked-children="启用"
                  un-checked-children="关闭"
                  @change="handleAccountSwitchToggle"
                />
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
import { message, Modal } from 'ant-design-vue'
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
    ProxyTimesLimit: number
    RunTimesLimit: number
    IfAccountSwitch: boolean
    GamePath: string
    ControllerType: 'Win32-Window' | 'Win32-Window-Background' | 'Win32-Front' | 'ADB'
  }
  MaaEnd: {
    ResourceProfile: string
    PresetTask: string
    ConfigLocked: boolean
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

const scriptId = route.params.id as string

const config = reactive<MaaEndScriptConfigLocal>({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    Timeout: 10,
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    IfAccountSwitch: false,
    GamePath: '',
    ControllerType: 'Win32-Window',
  },
  MaaEnd: {
    ResourceProfile: '',
    PresetTask: '',
    ConfigLocked: false,
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

const normalizeControllerType = (
  value: string | null | undefined
): 'Win32-Window' | 'Win32-Window-Background' | 'Win32-Front' | 'ADB' => {
  if (
    value === 'Win32-Window' ||
    value === 'Win32-Window-Background' ||
    value === 'Win32-Front' ||
    value === 'ADB'
  ) {
    return value
  }

  return 'Win32-Window'
}

const applyConfig = (rawConfig: any, nameFallback = '新建MaaEnd脚本') => {
  config.Info.Name = rawConfig?.Info?.Name ?? nameFallback
  config.Info.Path = rawConfig?.Info?.Path ?? '.'

  config.Run.Timeout = rawConfig?.Run?.Timeout ?? 10
  config.Run.ProxyTimesLimit = rawConfig?.Run?.ProxyTimesLimit ?? 0
  config.Run.RunTimesLimit = rawConfig?.Run?.RunTimesLimit ?? 3
  config.Run.IfAccountSwitch = rawConfig?.Run?.IfAccountSwitch ?? false
  config.Run.GamePath = rawConfig?.Run?.GamePath ?? ''
  config.Run.ControllerType = normalizeControllerType(rawConfig?.Run?.ControllerType)

  config.MaaEnd.ResourceProfile = rawConfig?.MaaEnd?.ResourceProfile ?? ''
  config.MaaEnd.PresetTask = rawConfig?.MaaEnd?.PresetTask ?? ''
  config.MaaEnd.ConfigLocked = rawConfig?.MaaEnd?.ConfigLocked ?? false
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

const handleAccountSwitchToggle = (checked: boolean) => {
  if (isInitializing.value) {
    return
  }

  if (!checked) {
    config.Run.IfAccountSwitch = false
    void handleChange('Run', 'IfAccountSwitch', false)
    return
  }

  Modal.confirm({
    title: '启用切号授权说明',
    content:
      '启用切号即表示您授权 AUTO-MAS 在自动化流程中代您同意鹰角网络相关用户协议并执行切号登录操作。是否继续？',
    okText: '同意并启用',
    cancelText: '取消',
    onOk: async () => {
      config.Run.IfAccountSwitch = true
      await handleChange('Run', 'IfAccountSwitch', true)
    },
    onCancel: () => {
      config.Run.IfAccountSwitch = false
    },
  })
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
    message.success('MaaEnd 路径选择成功')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择 MaaEnd 路径失败: ${errorMsg}`)
    message.error('选择文件夹失败')
  }
}

const selectGamePath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const selected = await (window.electronAPI as any).selectFile([
      { name: '可执行文件', extensions: ['exe'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    const path = Array.isArray(selected) ? selected[0] : selected
    if (!path) {
      return
    }

    config.Run.GamePath = path
    await handleChange('Run', 'GamePath', path)
    message.success('Endfield 路径选择成功')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择 Endfield 路径失败: ${errorMsg}`)
    message.error('选择 Endfield 路径失败')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(async () => {
  await loadScript()
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
