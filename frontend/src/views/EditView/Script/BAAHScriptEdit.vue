<template>
  <ScriptEditHeader script-type="BAAH" :title="t('edit.editScript')" @cancel="handleCancel" />

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
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
                    :disabled="item.disabled"
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
          <ScriptHardTimeoutField
            v-model:value="baahConfig.Run.HardTimeLimit"
            @save="handleChange('Run', 'HardTimeLimit', baahConfig.Run.HardTimeLimit)"
          />
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
  </ConfigLockPanel>
</template>

<script setup lang="ts">
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import ScriptHardTimeoutField from '@/views/EditView/Script/components/ScriptHardTimeoutField.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FileOutlined, FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'
import { useEmulatorOptions } from '@/composables/useEmulatorOptions'
import { useEmulatorDeviceOptions } from '@/composables/useEmulatorDeviceOptions.ts'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('BAAH脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, error: scriptApiError } = useScriptApi()
const {
  emulatorDeviceLoading,
  emulatorDeviceOptions,
  clearEmulatorDeviceOptions,
  loadEmulatorDeviceOptions,
} = useEmulatorDeviceOptions()

// 模拟器相关状态：模拟器的启动与关闭由本软件调度，BAAH 只负责连接
const { emulatorLoading, emulatorOptions, loadEmulatorOptions } = useEmulatorOptions()

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isInitializing = ref(true)
const {
  isSaving,
  save,
  saveField: handleChange,
} = useScriptSaveMutation({ scriptId, isInitializing, logger })

interface BAAHInfoForm {
  Name: string
}

interface BAAHScriptForm {
  BAAHPath: string
  IfManageConfig: boolean
  PushLogEnabled: boolean
}

interface BAAHRunForm {
  HardTimeLimit: number
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
  Run: { HardTimeLimit: 120, RunTimesLimit: 2, RunTimeLimit: 60 },
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

const loadScript = async () => {
  pageLoading.value = true
  isInitializing.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail) {
      if (!scriptApiError.value) message.error(t('edit.scriptDoesNotExist'))
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
    if (!scriptApiError.value) message.error(t('edit.couldNotLoadScript'))
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
const handleEmulatorSelectChange = async (emulatorId: string) => {
  // 换模拟器后旧的实例索引不再有效
  baahConfig.Emulator.Index = ''
  if (emulatorId) {
    void loadEmulatorDeviceOptions(emulatorId)
  } else {
    clearEmulatorDeviceOptions()
  }

  // 模拟器和清空实例一起落盘，避免等待期间选的新实例又被清空。
  await save({ Emulator: { Id: emulatorId, Index: '' } })
}

onMounted(() => {
  void loadScript()
  void loadEmulatorOptions()
})
</script>

<style scoped src="@/styles/scriptEditForm.css"></style>

<style scoped>
.section-header {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  gap: 8px;
}

.modern-input {
  border-radius: 8px;
}

.path-input-group {
  border: 1px solid var(--ant-color-border);
}

.path-input {
  min-width: 0;
}

.path-button {
  flex-shrink: 0;
}
</style>
