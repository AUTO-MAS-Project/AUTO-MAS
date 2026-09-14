<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/baah.png" alt="BAAH" class="breadcrumb-logo" />
            {{ t('edit.editScript') }}
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('edit.back') }}
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card :title="t('edit.baahScriptConfiguration')" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="magenta" class="type-tag">BAAH</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="24">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.scriptName') }}
                    <a-tooltip :title="t('edit.baahScriptNameHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  :placeholder="t('edit.enterScriptName')"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 脚本配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.scriptConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.mainProgramPath') }}
                    <a-tooltip :title="t('edit.baahScriptPathHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.baahPath"
                    :placeholder="t('edit.pickScriptSMain')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="isSaving"
                    @click="selectBaahPath"
                  >
                    <template #icon>
                      <FileOutlined />
                    </template>
                    {{ t('edit.pickFile') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.baahManageConfig') }}
                    <a-tooltip :title="t('edit.baahManageConfigHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="baahConfig.Script.IfManageConfig"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Script', 'IfManageConfig', $event)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.baahPushLogEnabled') }}
                    <a-tooltip :title="t('edit.baahPushLogEnabledHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="baahConfig.Script.PushLogEnabled"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Script', 'PushLogEnabled', $event)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>

          <!-- 关闭托管时 BAAH 会用它自己的设置启动模拟器，两边抢同一台设备 -->
          <a-alert
            type="warning"
            show-icon
            :message="t('edit.baahAutoStartNotice')"
            style="margin-top: 16px"
          />
        </div>

        <!-- 模拟器管理 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.emulators') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.emulator') }}
                    <a-tooltip :title="t('edit.baahEmulatorHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="baahConfig.Emulator.Id"
                  size="large"
                  :placeholder="t('edit.pickEmulator')"
                  :loading="emulatorLoading"
                  @change="handleEmulatorSelectChange"
                >
                  <a-select-option
                    v-for="item in emulatorOptions"
                    :key="item.value"
                    :value="item.value"
                  >
                    {{ item.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.emulatorInstance') }}
                    <a-tooltip :title="t('edit.pickEmulatorInstance')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <!-- 当API返回空列表时显示输入框 -->
                <a-input
                  v-if="
                    emulatorDeviceOptions.length === 0 &&
                    !emulatorDeviceLoading &&
                    baahConfig.Emulator.Id
                  "
                  v-model:value="baahConfig.Emulator.Index"
                  size="large"
                  :placeholder="t('edit.enterInstanceInfoAs')"
                  class="modern-input"
                  @blur="handleChange('Emulator', 'Index', baahConfig.Emulator.Index)"
                />
                <!-- 正常情况下显示下拉框 -->
                <a-select
                  v-else
                  v-model:value="baahConfig.Emulator.Index"
                  size="large"
                  :placeholder="t('edit.pickEmulatorFirst')"
                  :loading="emulatorDeviceLoading"
                  :disabled="!baahConfig.Emulator.Id"
                  @change="handleChange('Emulator', 'Index', $event)"
                >
                  <a-select-option
                    v-for="item in emulatorDeviceOptions"
                    :key="item.value"
                    :value="item.value"
                  >
                    {{ item.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 运行配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.runConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.baahRunTimesLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="baahConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', baahConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.baahRunTimeLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="baahConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', baahConfig.Run.RunTimeLimit)"
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  FileOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useEmulatorDeviceOptions } from '@/composables/useEmulatorDeviceOptions.ts'
import { Service, type ComboBoxItem } from '@/api'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('BAAH脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()
const {
  emulatorDeviceLoading,
  emulatorDeviceOptions,
  clearEmulatorDeviceOptions,
  loadEmulatorDeviceOptions,
} = useEmulatorDeviceOptions()

// 模拟器相关状态：模拟器的启动与关闭由本软件调度，BAAH 只负责连接
const emulatorLoading = ref(false)
const emulatorOptions = ref<ComboBoxItem[]>([])

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isSaving = ref(false)
const isInitializing = ref(true)

interface BAAHInfoForm {
  Name: string
}

interface BAAHScriptForm {
  BAAHPath: string
  IfManageConfig: boolean
  PushLogEnabled: boolean
}

interface BAAHRunForm {
  RunTimesLimit: number
  RunTimeLimit: number
}

interface BAAHEmulatorForm {
  Id: string
  Index: string
}

interface BAAHScriptConfigForm {
  Info: BAAHInfoForm
  Script: BAAHScriptForm
  Run: BAAHRunForm
  Emulator: BAAHEmulatorForm
}

const getDefaultBAAHConfig = (): BAAHScriptConfigForm => ({
  Info: {
    Name: '',
  },
  Script: {
    BAAHPath: '',
    IfManageConfig: true,
    PushLogEnabled: true,
  },
  Run: {
    RunTimesLimit: 2,
    RunTimeLimit: 60,
  },
  Emulator: {
    Id: '',
    Index: '',
  },
})

const baahConfig = reactive<BAAHScriptConfigForm>(getDefaultBAAHConfig())

// 表单绑定代理：Info/Run 直接读写 baahConfig，避免出现两份真相
const formData = reactive({
  get name() {
    return baahConfig.Info.Name
  },
  set name(value: string) {
    baahConfig.Info.Name = value
  },
  get baahPath() {
    return baahConfig.Script.BAAHPath
  },
  set baahPath(value: string) {
    baahConfig.Script.BAAHPath = value
  },
})

const rules = computed(() => ({
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
}))

// 统一使用正斜杠落盘，与后端 FolderValidator/FileValidator 的取值保持一致
const normalizePath = (path: string) => path.replace(/\\/g, '/').replace(/\/+$/, '')

// 局部更新：只提交变更的那个字段，不整体覆盖脚本配置
const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
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

const loadScript = async () => {
  pageLoading.value = true
  isInitializing.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail) {
      message.error(t('edit.scriptDoesNotExist'))
      handleCancel()
      return
    }
    if (detail.type !== 'BAAH') {
      message.error(t('edit.baahNotBaahScript'))
      handleCancel()
      return
    }
    const config = detail.config as Partial<BAAHScriptConfigForm>
    Object.assign(baahConfig.Info, config.Info || {})
    Object.assign(baahConfig.Script, config.Script || {})
    Object.assign(baahConfig.Run, config.Run || {})
    Object.assign(baahConfig.Emulator, config.Emulator || {})
    // 已经选过模拟器时同步加载它的设备列表
    if (baahConfig.Emulator.Id) {
      void loadEmulatorDeviceOptions(baahConfig.Emulator.Id)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadScript'))
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const handleCancel = () => router.push('/scripts')

const selectBaahPath = async () => {
  const paths = await window.electronAPI?.selectFile([
    { name: 'BAAH.exe', extensions: ['exe'] },
    { name: t('edit.allFiles'), extensions: ['*'] },
  ])
  const path = paths?.[0]
  if (!path) return
  const normalized = normalizePath(path)
  baahConfig.Script.BAAHPath = normalized
  await handleChange('Script', 'BAAHPath', normalized)
}

// 模拟器相关方法
const loadEmulatorOptions = async () => {
  emulatorLoading.value = true
  try {
    const response = await Service.getEmulatorComboxApiInfoComboxEmulatorPost()
    emulatorOptions.value = response.data || []
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模拟器选项失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadEmulator'))
  } finally {
    emulatorLoading.value = false
  }
}

const handleEmulatorSelectChange = async (emulatorId: string) => {
  // 换模拟器后旧的实例索引不再有效
  baahConfig.Emulator.Index = ''
  if (emulatorId) {
    void loadEmulatorDeviceOptions(emulatorId)
  } else {
    clearEmulatorDeviceOptions()
  }

  await handleChange('Emulator', 'Id', emulatorId)
  await handleChange('Emulator', 'Index', '')
}

onMounted(() => {
  void loadScript()
  void loadEmulatorOptions()
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
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
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
}

.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
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
}

.path-input-group {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  min-width: 0;
  border: none !important;
  border-radius: 0 !important;
}

.path-button {
  flex-shrink: 0;
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.cancel-button:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
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
</style>
