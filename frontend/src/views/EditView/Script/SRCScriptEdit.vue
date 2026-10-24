<template>
  <ScriptEditHeader script-type="SRC" :title="t('edit.editScript')" @cancel="handleCancel" />

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card :title="t('edit.srcScriptConfiguration')" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="blue" class="type-tag"> SRC </a-tag>
      </template>

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <a-tooltip :title="t('edit.giveScriptNameYou')">
                    <span class="form-label">
                      {{ t('edit.scriptName') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
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
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <a-tooltip :title="t('edit.pickFolderHoldingSrc2')">
                    <span class="form-label">
                      {{ t('edit.srcPath') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    :placeholder="t('edit.pickFolderHoldingSrc')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectSRCPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickFolder') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 模拟器管理 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.emulators') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.pickEmulatorUse')">
                    <span class="form-label">
                      {{ t('edit.emulator') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="srcConfig.Emulator.Id"
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
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    :title="
                      emulatorDeviceOptions.length === 0 && !emulatorDeviceLoading
                        ? t('edit.thisEmulatorCannotBe')
                        : t('edit.pickEmulatorInstance')
                    "
                  >
                    <span class="form-label">
                      {{ t('edit.emulatorInstance') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <!-- 当API返回空列表时显示输入框 -->
                <a-input
                  v-if="
                    emulatorDeviceOptions.length === 0 &&
                    !emulatorDeviceLoading &&
                    srcConfig.Emulator.Id
                  "
                  v-model:value="srcConfig.Emulator.Index"
                  size="large"
                  :placeholder="t('edit.enterInstanceInfoAs')"
                  class="modern-input"
                  @blur="handleChange('Emulator', 'Index', srcConfig.Emulator.Index)"
                />
                <!-- 正常情况下显示下拉框 -->
                <a-select
                  v-else
                  v-model:value="srcConfig.Emulator.Index"
                  size="large"
                  :placeholder="t('edit.pickEmulatorFirst')"
                  :loading="emulatorDeviceLoading"
                  :disabled="!srcConfig.Emulator.Id"
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
            v-model:value="srcConfig.Run.HardTimeLimit"
            @save="handleChange('Run', 'HardTimeLimit', srcConfig.Run.HardTimeLimit)"
          />
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.whatDoWhenSwitching')">
                    <span class="form-label">
                      {{ t('edit.accountSwitchingMethod') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="srcConfig.Run.TaskTransitionMethod"
                  size="large"
                  @change="handleChange('Run', 'TaskTransitionMethod', $event)"
                >
                  <a-select-option value="ExitEmulator">{{
                    t('edit.restartEmulator')
                  }}</a-select-option>
                  <a-select-option value="ExitGame">{{ t('edit.restartGame') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.skipRunOnceThis')">
                    <span class="form-label">
                      {{ t('edit.runsPerDayThis') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="srcConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', srcConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.ifRunStillUnfinished')">
                    <span class="form-label">
                      {{ t('edit.retryLimit') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="srcConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', srcConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.treatRunAsTimed2')">
                    <span class="form-label">
                      {{ t('edit.runTimeoutMinutes2') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="srcConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', srcConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 游戏更新 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.gameUpdate') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.checkGameUpdateBeforeLogin')">
                    <span class="form-label">
                      {{ t('edit.checkGameUpdateBefore') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="srcConfig.Run.IfCheckGameUpdate"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Run', 'IfCheckGameUpdate', $event)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.whenClientDetectedAs')">
                    <span class="form-label">
                      {{ t('edit.installGamePackageAutomatically') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="srcConfig.Run.IfAutoInstallGameApk"
                  size="large"
                  style="width: 100%"
                  :disabled="!srcConfig.Run.IfCheckGameUpdate"
                  @change="handleChange('Run', 'IfAutoInstallGameApk', $event)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.timeoutDownloadingInstallingGame')">
                    <span class="form-label">
                      {{ t('edit.gameUpdateTimeoutMinutes') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="srcConfig.Run.GameUpdateTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  :disabled="!srcConfig.Run.IfCheckGameUpdate"
                  @blur="
                    handleChange('Run', 'GameUpdateTimeLimit', srcConfig.Run.GameUpdateTimeLimit)
                  "
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
import { createSrcScriptDraft } from './srcScriptDraft'
import ScriptHardTimeoutField from '@/views/EditView/Script/components/ScriptHardTimeoutField.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { useI18n } from 'vue-i18n'
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { SRCScriptConfig, ScriptType } from '@/types/script.ts'
import { useEmulatorDeviceOptions } from '@/composables/useEmulatorDeviceOptions.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useEmulatorOptions } from '@/composables/useEmulatorOptions'
import { FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('SRC脚本编辑')

const route = useRoute()
const router = useRouter()
const { getScript, updateScript, error: scriptApiError } = useScriptApi()
const {
  emulatorDeviceLoading,
  emulatorDeviceOptions,
  clearEmulatorDeviceOptions,
  loadEmulatorDeviceOptions,
} = useEmulatorDeviceOptions()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true) // 标记是否正在初始化
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { enqueue } = useSaveQueue()

const formData = reactive({
  name: '',
  type: 'SRC' as ScriptType,
  get path() {
    return srcConfig.Info?.Path || '.'
  },
  set path(value) {
    if (srcConfig.Info) {
      srcConfig.Info.Path = value
    }
  },
})

// SRC配置
const srcConfig = reactive(createSrcScriptDraft())

const rules = {
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
  type: [{ required: true, message: t('edit.pickScriptType'), trigger: 'change' }],
  path: [{ required: true, message: t('edit.pickSrcPath'), trigger: 'blur' }],
}

// 模拟器相关状态
const { emulatorLoading, emulatorOptions, loadEmulatorOptions } = useEmulatorOptions()

// 即时保存函数 - 只发送修改的字段（遵循最小原则）
// 后端会把这些路径字段规范化（相对路径转绝对、展开 %APPDATA%、解析 .lnk 等），
// 保存后只回读这一个字段，界面才与落盘值一致；其余字段保存即生效不再整份回读
const FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set<string>(['Info.Path'])

const refreshNormalizedField = async (category: string, key: string) => {
  const scriptDetail = await getScript(scriptId)
  const normalized = (scriptDetail?.config as Record<string, any> | undefined)?.[category]?.[key]
  if (normalized !== undefined) {
    ;(srcConfig as Record<string, any>)[category][key] = normalized
  }
}

const handleChange = async (category: string, key: string, value: any) => {
  if (isInitializing.value) return

  await enqueue(async () => {
    try {
      // 构建只包含单个修改字段的更新数据（遵循最小原则）
      const updateData: any = { [category]: { [key]: value } }

      const success = await updateScript(scriptId, updateData)
      if (success) {
        logger.info(`配置已保存: ${category}.${key}`)
        if (FIELDS_REQUIRE_REFRESH_AFTER_SAVE.has(`${category}.${key}`)) {
          await refreshNormalizedField(category, key)
        }
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
    }
  }, `${category}.${key}`)
}

onMounted(async () => {
  // 两个请求互不依赖, 并行发出
  await Promise.all([loadScript(), loadEmulatorOptions()])
  // 初始化完成后允许自动保存
  isInitializing.value = false
})

const loadScript = async () => {
  pageLoading.value = true
  try {
    // 检查是否有通过路由状态传递的数据（新建脚本时）
    const routeState = history.state as any
    if (routeState?.scriptData) {
      // 有路由状态数据时，先使用它快速渲染，但仍然从API重新加载以确保数据完整性
      const scriptData = routeState.scriptData
      const config = scriptData.config as SRCScriptConfig
      formData.name = config.Info?.Name || '新建SRC脚本'
      Object.assign(srcConfig, config)

      // 从API重新加载完整数据（确保包含所有必要的配置）
      const scriptDetail = await getScript(scriptId)
      if (scriptDetail) {
        formData.type = scriptDetail.type
        formData.name = scriptDetail.name
        Object.assign(srcConfig, scriptDetail.config as SRCScriptConfig)
      }

      // 如果已经有选择的模拟器，加载对应的设备选项
      if (srcConfig.Emulator?.Id) {
        void loadEmulatorDeviceOptions(srcConfig.Emulator.Id)
      }
    } else {
      // 编辑现有脚本时，从API获取数据
      const scriptDetail = await getScript(scriptId)

      if (!scriptDetail) {
        if (!scriptApiError.value) message.error(t('edit.scriptDoesNotExist'))
        router.push('/scripts')
        return
      }

      formData.type = scriptDetail.type
      formData.name = scriptDetail.name

      Object.assign(srcConfig, scriptDetail.config as SRCScriptConfig)

      // 如果已经有选择的模拟器，加载对应的设备选项
      if (srcConfig.Emulator?.Id) {
        void loadEmulatorDeviceOptions(srcConfig.Emulator.Id)
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    if (!scriptApiError.value) message.error(t('edit.couldNotLoadScript'))
    router.push('/scripts')
  } finally {
    pageLoading.value = false
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// 模拟器相关方法
const handleEmulatorSelectChange = async (emulatorId: string) => {
  // 清空模拟器实例选择
  srcConfig.Emulator.Index = ''
  if (emulatorId) {
    void loadEmulatorDeviceOptions(emulatorId)
  } else {
    clearEmulatorDeviceOptions()
  }

  // 保存模拟器选择和清空的实例字段
  await enqueue(async () => {
    try {
      const updateData = {
        Emulator: {
          Id: emulatorId,
          Index: '',
        },
      }
      const success = await updateScript(scriptId, updateData)
      if (success) {
        logger.info('模拟器配置已保存')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存模拟器配置失败: ${errorMsg}`)
    }
  })
}

// 文件选择方法
const selectSRCPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error(t('edit.filePickingUnavailableRun'))
      return
    }

    const path = await window.electronAPI.selectFolder()
    if (path) {
      if (!srcConfig.Info) {
        srcConfig.Info = { Name: '', Path: '' }
      }
      srcConfig.Info.Path = path
      // 选择路径后立即保存
      await handleChange('Info', 'Path', path)
      message.success(t('edit.srcPathSelected'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择SRC路径失败: ${errorMsg}`)
    message.error(t('edit.couldNotPickFolder'))
  }
}
</script>

<style scoped src="@/styles/scriptEditForm.css"></style>

<style scoped src="@/styles/scriptEdit.css"></style>
