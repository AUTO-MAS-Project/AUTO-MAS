<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="../../../assets/MaaEnd.png" alt="MaaEnd" class="breadcrumb-logo" />
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
        <a-tag class="type-tag">MaaEnd</a-tag>
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
                    <a-tooltip title="用于区分不同的 MaaEnd 脚本实例">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input v-model:value="formData.name" placeholder="请输入脚本名称" size="large" class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.name)" />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <span class="form-label">
                    MaaEnd 路径
                    <a-tooltip title="选择 MaaEnd.exe 所在目录">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input v-model:value="formData.path" placeholder="请选择 MaaEnd.exe 所在目录" size="large"
                    class="path-input" readonly />
                  <a-button size="large" class="path-button" @click="selectMaaEndPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择目录
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>游戏配置</h3>
          </div>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    控制器
                    <a-tooltip title="选择游戏控制方式">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select v-model:value="maaEndConfig.Game.ControllerType" size="large" :options="controllerOptions"
                  @change="handleControllerTypeChange" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    任务结束后关闭游戏
                    <a-tooltip title="自动登录任务结束后是否关闭游戏">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select v-model:value="maaEndConfig.Game.CloseOnFinish" size="large" :options="booleanOptions"
                  @change="handleChange('Game', 'CloseOnFinish', $event)" />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row v-if="isWinController" :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    游戏路径
                    <a-tooltip title="选择游戏本体可执行文件的路径">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input v-model:value="maaEndConfig.Game.Path" placeholder="请选择游戏可执行文件" size="large"
                    class="path-input" readonly />
                  <a-button size="large" class="path-button" @click="selectGamePath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    启动参数
                    <a-tooltip title="启动游戏时的命令行参数">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input v-model:value="maaEndConfig.Game.Arguments" placeholder="请输入启动参数" size="large"
                  class="modern-input" @blur="handleChange('Game', 'Arguments', maaEndConfig.Game.Arguments)" />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    等待时间
                    <a-tooltip title="仅电脑端控制器需要配置，单位秒">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number v-model:value="maaEndConfig.Game.WaitTime" :min="0" :max="9999" size="large"
                  style="width: 100%" @blur="handleChange('Game', 'WaitTime', maaEndConfig.Game.WaitTime)" />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row v-else :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    模拟器
                    <a-tooltip title="选择要使用的模拟器">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select v-model:value="maaEndConfig.Game.EmulatorId" size="large" placeholder="请选择模拟器"
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
                  <span class="form-label">
                    模拟器实例
                    <a-tooltip
                      :title="emulatorDeviceOptions.length === 0 && !emulatorDeviceLoading ? '不支持自动扫描实例的模拟器，请手动输入实例信息' : '选择模拟器的具体实例'">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input v-if="showManualEmulatorIndexInput" v-model:value="maaEndConfig.Game.EmulatorIndex"
                  size="large" class="modern-input" placeholder="请输入实例信息，格式：启动附加命令 | ADB地址"
                  @blur="handleChange('Game', 'EmulatorIndex', maaEndConfig.Game.EmulatorIndex)" />
                <a-select v-else v-model:value="maaEndConfig.Game.EmulatorIndex" size="large" placeholder="请选择实例"
                  :loading="emulatorDeviceLoading" :disabled="!maaEndConfig.Game.EmulatorId"
                  @change="handleChange('Game', 'EmulatorIndex', $event)">
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
                  <span class="form-label">
                    单日代理次数上限
                    <a-tooltip title="当用户本日代理成功次数达到该阀值时跳过代理，阈值为「0」时视为无代理次数上限">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number v-model:value="maaEndConfig.Run.ProxyTimesLimit" :min="0" :max="9999" size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', maaEndConfig.Run.ProxyTimesLimit)" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    重试次数限制
                    <a-tooltip title="若重试超过该次数限制仍未完成代理，视为代理失败">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number v-model:value="maaEndConfig.Run.RunTimesLimit" :min="1" :max="9999" size="large"
                  style="width: 100%" @blur="handleChange('Run', 'RunTimesLimit', maaEndConfig.Run.RunTimesLimit)" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    代理超时限制（分钟）
                    <a-tooltip title="执行代理任务时，脚本日志无变化时间超过该阀值视为超时">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number v-model:value="maaEndConfig.Run.RunTimeLimit" :min="1" :max="9999" size="large"
                  style="width: 100%" @blur="handleChange('Run', 'RunTimeLimit', maaEndConfig.Run.RunTimeLimit)" />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { ComboBoxItem } from '@/api'
import { Service } from '@/api'
import type { MaaEndScriptConfig, ScriptType } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true)
const isSaving = ref(false)

const formData = reactive({
  name: '',
  type: 'MaaEnd' as ScriptType,
  get path() {
    return maaEndConfig.Info.Path
  },
  set path(value: string) {
    maaEndConfig.Info.Path = value
  },
})

const maaEndConfig = reactive<MaaEndScriptConfig>({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    RunTimeLimit: 30,
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
  },
  Game: {
    ControllerType: 'Win32-Window',
    Path: '',
    Arguments: '',
    WaitTime: 60,
    EmulatorId: '',
    EmulatorIndex: '',
    CloseOnFinish: false,
  },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  path: [{ required: true, message: '请选择 MaaEnd 路径', trigger: 'blur' }],
}

const controllerOptions = [
  { label: '电脑端-通用', value: 'Win32-Window' },
  { label: '电脑端-后台', value: 'Win32-Window-Background' },
  { label: '电脑端-前台', value: 'Win32-Front' },
  { label: '安卓端', value: 'ADB' },
]

const booleanOptions = [
  { label: '是', value: true },
  { label: '否', value: false },
]

const emulatorLoading = ref(false)
const emulatorDeviceLoading = ref(false)
const emulatorOptions = ref<ComboBoxItem[]>([])
const emulatorDeviceOptions = ref<ComboBoxItem[]>([])

const isWinController = computed(() => maaEndConfig.Game.ControllerType !== 'ADB')
const showManualEmulatorIndexInput = computed(
  () =>
    emulatorDeviceOptions.value.length === 0 &&
    !emulatorDeviceLoading.value &&
    Boolean(maaEndConfig.Game.EmulatorId)
)

const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      [category]: { [key]: value },
    })
    if (success) {
      await refreshScript()
    }
  } finally {
    isSaving.value = false
  }
}

const refreshScript = async () => {
  const scriptDetail = await getScript(scriptId)
  if (!scriptDetail) return
  Object.assign(maaEndConfig, scriptDetail.config as MaaEndScriptConfig)
  formData.name = scriptDetail.name
}

const loadEmulatorOptions = async () => {
  emulatorLoading.value = true
  try {
    const response = await Service.getEmulatorComboxApiInfoComboxEmulatorPost()
    if (response.code === 200) {
      emulatorOptions.value = response.data || []
    }
  } finally {
    emulatorLoading.value = false
  }
}

const loadEmulatorDeviceOptions = async (emulatorId: string) => {
  if (!emulatorId) return

  emulatorDeviceLoading.value = true
  try {
    const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
      emulatorId,
    })
    if (response.code === 200) {
      emulatorDeviceOptions.value = response.data || []
    }
  } finally {
    emulatorDeviceLoading.value = false
  }
}

const loadScript = async () => {
  pageLoading.value = true
  try {
    const routeState = history.state as any
    if (routeState?.scriptData) {
      const config = routeState.scriptData.config as MaaEndScriptConfig
      formData.name = config.Info?.Name || '新建 MaaEnd 脚本'
      Object.assign(maaEndConfig, config)
    }

    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) {
      message.error('脚本不存在或加载失败')
      router.push('/scripts')
      return
    }

    formData.type = scriptDetail.type
    formData.name = scriptDetail.name
    Object.assign(maaEndConfig, scriptDetail.config as MaaEndScriptConfig)

    if (maaEndConfig.Game.EmulatorId) {
      await loadEmulatorDeviceOptions(maaEndConfig.Game.EmulatorId)
    }
  } finally {
    pageLoading.value = false
  }
}

const handleControllerTypeChange = async (value: MaaEndScriptConfig['Game']['ControllerType']) => {
  isSaving.value = true
  try {
    const gamePayload =
      value === 'ADB'
        ? {
          ControllerType: value,
          Path: '',
          Arguments: '',
          WaitTime: 15,
        }
        : {
          ControllerType: value,
          EmulatorId: '',
          EmulatorIndex: '',
        }

    if (value !== 'ADB') {
      emulatorDeviceOptions.value = []
      maaEndConfig.Game.EmulatorId = ''
      maaEndConfig.Game.EmulatorIndex = ''
    } else {
      maaEndConfig.Game.Path = ''
      maaEndConfig.Game.Arguments = ''
    }

    const success = await updateScript(scriptId, { Game: gamePayload })
    if (success) {
      await refreshScript()
    }
  } finally {
    isSaving.value = false
  }

  if (value === 'ADB') {
    await loadEmulatorOptions()
  }
}

const handleEmulatorSelectChange = async (emulatorId: string) => {
  maaEndConfig.Game.EmulatorIndex = ''
  emulatorDeviceOptions.value = []

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Game: {
        EmulatorId: emulatorId,
        EmulatorIndex: '',
      },
    })
    if (success) {
      await refreshScript()
    }
  } finally {
    isSaving.value = false
  }

  if (emulatorId) {
    await loadEmulatorDeviceOptions(emulatorId)
  }
}

const selectMaaEndPath = async () => {
  const path = await window.electronAPI?.selectFolder()
  if (!path) return
  maaEndConfig.Info.Path = path
  await handleChange('Info', 'Path', path)
}

const selectGamePath = async () => {
  const paths = await window.electronAPI?.selectFile([
    {
      name: 'Executable',
      extensions: ['exe'],
    },
  ])
  const path = paths?.[0]
  if (!path) return
  maaEndConfig.Game.Path = path
  await handleChange('Game', 'Path', path)
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(async () => {
  await loadScript()
  await loadEmulatorOptions()
  isInitializing.value = false
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

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--ant-color-primary-border);
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.form-section {
  margin-bottom: 12px;
  animation: fadeInUp 0.6s ease-out;
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
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
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
</style>
