<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section form-section-alt">
    <div class="section-header">
      <h3>控制方式与游戏资源</h3>
    </div>

    <a-row :gutter="24" class="controller-resource-row">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip title="选择 MaaFW Controller，决定使用 ADB、Win32 等控制方式">
              <span class="form-label">
                控制方式
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Info.Controller"
            size="large"
            placeholder="自动选择"
            allow-clear
            :disabled="interfaceDependentDisabled"
            @change="emit('controller-change')"
          >
            <a-select-option
              v-for="item in controllerOptions"
              :key="item.name"
              :value="item.name"
              :disabled="!isDirectControllerType(item.type)"
            >
              {{ item.label || item.name }} · {{ item.type }}
              <span v-if="!isDirectControllerType(item.type)"> · 建议使用原 UI</span>
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip title="选择 MaaFW Resource，留空时自动选择匹配当前控制方式的第一个 Resource">
              <span class="form-label">
                游戏资源
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Info.Resource"
            size="large"
            placeholder="自动选择"
            allow-clear
            :disabled="interfaceDependentDisabled"
            @change="emit('resource-change')"
          >
            <a-select-option v-for="item in resourceOptions" :key="item.name" :value="item.name">
              {{ item.label || item.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>
    <a-alert
      v-if="unsupportedControllerOptions.length"
      class="control-strategy-alert"
      type="info"
      show-icon
      :message="unsupportedControllerMessage"
    />

    <Transition name="control-fade" mode="out-in">
      <div v-if="isAdbController" key="adb">
        <a-row :gutter="24" class="control-detail-row">
          <a-col :span="12">
            <a-form-item>
              <template #label>
                <a-tooltip title="MaaFW ADB controller 运行时使用该模拟器配置">
                  <span class="form-label">
                    模拟器
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="maafwConfig.Emulator.Id"
                size="large"
                placeholder="请选择模拟器"
                :loading="emulatorLoading"
                :disabled="!emulatorOptionsReady"
                @change="(value: string | number) => emit('emulator-select-change', String(value))"
              >
                <a-select-option value="-">不指定</a-select-option>
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
                <a-tooltip title="选择模拟器的具体实例，运行时会传递给 MaaFW ADB controller">
                  <span class="form-label">
                    模拟器实例
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-if="
                  emulatorDeviceOptions.length === 0 &&
                  !emulatorDeviceLoading &&
                  maafwConfig.Emulator.Id &&
                  maafwConfig.Emulator.Id !== '-'
                "
                v-model:value="maafwConfig.Emulator.Index"
                size="large"
                placeholder="请输入模拟器实例索引"
                class="modern-input"
                :disabled="!emulatorOptionsReady"
                @blur="emit('change', 'Emulator', 'Index', maafwConfig.Emulator.Index)"
              />
              <a-select
                v-else
                v-model:value="maafwConfig.Emulator.Index"
                size="large"
                placeholder="请先选择模拟器"
                :loading="emulatorDeviceLoading"
                :disabled="
                  !emulatorOptionsReady ||
                  emulatorDeviceLoading ||
                  !maafwConfig.Emulator.Id ||
                  maafwConfig.Emulator.Id === '-'
                "
                @change="(value: string | number) => emit('change', 'Emulator', 'Index', value)"
              >
                <a-select-option value="-">不指定</a-select-option>
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

        <a-alert
          class="control-strategy-alert"
          type="info"
          show-icon
          :message="adbControlStrategyMessage"
        />
        <a-descriptions :column="3" size="small" bordered class="control-strategy-summary">
          <a-descriptions-item
            v-for="item in adbControlStrategyItems"
            :key="item.label"
            :label="item.label"
          >
            {{ item.value }}
          </a-descriptions-item>
        </a-descriptions>
      </div>

      <div v-else-if="isDesktopController" key="win32">
        <a-alert
          class="control-strategy-alert"
          type="info"
          show-icon
          message="Win32 控制方式支持启动与检测分离：启动目标只负责拉起程序，检测目标负责定位实际游戏窗口。"
        />

        <a-form-item>
          <template #label>
            <span class="form-label">PC 游戏启动方式</span>
          </template>
          <a-select
            v-model:value="maafwConfig.Game.LaunchMode"
            size="large"
            style="width: 100%"
            @change="emit('change', 'Game', 'LaunchMode', maafwConfig.Game.LaunchMode)"
          >
            <a-select-option value="AttachOnly">仅附加，不主动启动</a-select-option>
            <a-select-option value="DirectExe">直接启动游戏 exe</a-select-option>
            <a-select-option value="LauncherExe">启动器 exe，再附加游戏</a-select-option>
            <a-select-option value="URL">启动协议 URL，再附加游戏</a-select-option>
          </a-select>
          <div class="field-help">{{ launchModeDescription }}</div>
        </a-form-item>

        <a-row :gutter="24" class="control-detail-row">
          <a-col v-if="launchMode !== 'AttachOnly' && launchMode !== 'URL'" :span="12">
            <a-form-item>
              <template #label>
                <a-tooltip
                  :title="
                    launchMode === 'LauncherExe'
                      ? 'MAS 启动的启动器 exe；实际游戏由下方检测字段单独定位'
                      : 'MAS 直接启动的实际游戏 exe'
                  "
                >
                  <span class="form-label">
                    {{ launchMode === 'LauncherExe' ? '启动器可执行文件' : '游戏可执行文件' }}
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-group compact class="path-input-group">
                <a-input
                  v-model:value="maafwConfig.Game.LaunchPath"
                  :placeholder="
                    launchMode === 'LauncherExe' ? '请选择启动器 exe' : '请选择实际启动的游戏 exe'
                  "
                  size="large"
                  class="path-input"
                  readonly
                />
                <a-button size="large" class="path-button" @click="emit('select-launch-path')">
                  <template #icon>
                    <FolderOpenOutlined />
                  </template>
                  选择 exe
                </a-button>
              </a-input-group>
            </a-form-item>
          </a-col>
          <a-col v-if="launchMode === 'URL'" :span="12">
            <a-form-item>
              <template #label>
                <a-tooltip
                  title="使用系统协议处理器启动，例如 steam://、com.epicgames.launcher:// 等"
                >
                  <span class="form-label">
                    协议启动 URL
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="maafwConfig.Game.LaunchURL"
                placeholder="例如 steam://rungameid/123"
                size="large"
                class="modern-input"
                @blur="emit('change', 'Game', 'LaunchURL', maafwConfig.Game.LaunchURL)"
              />
            </a-form-item>
          </a-col>
          <a-col v-if="launchMode === 'DirectExe' || launchMode === 'LauncherExe'" :span="6">
            <a-form-item>
              <template #label>
                <a-tooltip title="仅 exe 启动模式会传递给启动目标的命令行参数">
                  <span class="form-label">
                    启动参数
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="maafwConfig.Game.Arguments"
                placeholder="可选"
                size="large"
                class="modern-input"
                @blur="emit('change', 'Game', 'Arguments', maafwConfig.Game.Arguments)"
              />
            </a-form-item>
          </a-col>
          <a-col v-if="launchMode !== 'AttachOnly'" :span="6">
            <a-form-item>
              <template #label>
                <a-tooltip title="启动目标后等待实际游戏进程/窗口出现的时间，单位秒">
                  <span class="form-label">
                    等待时间
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-number
                v-model:value="maafwConfig.Game.WaitTime"
                :min="0"
                :max="9999"
                size="large"
                style="width: 100%"
                @blur="emit('change', 'Game', 'WaitTime', maafwConfig.Game.WaitTime)"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24" class="control-detail-row">
          <a-col :span="12">
            <a-form-item>
              <template #label>
                <a-tooltip title="用于附加 MaaFW 的实际游戏进程；可与启动目标不同">
                  <span class="form-label">
                    目标进程路径
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="maafwConfig.Game.ProcessPath"
                placeholder="与目标进程名称至少填写一项"
                size="large"
                class="modern-input"
                @blur="emit('change', 'Game', 'ProcessPath', maafwConfig.Game.ProcessPath)"
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item>
              <template #label>
                <a-tooltip title="目标进程名称，例如 Game.exe；与目标进程路径二选一或同时填写">
                  <span class="form-label">
                    目标进程名称
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="maafwConfig.Game.ProcessName"
                placeholder="与目标进程路径至少填写一项"
                size="large"
                class="modern-input"
                @blur="emit('change', 'Game', 'ProcessName', maafwConfig.Game.ProcessName)"
              />
            </a-form-item>
          </a-col>
          <a-col v-if="launchMode !== 'AttachOnly'" :span="6">
            <a-form-item>
              <template #label>
                <a-tooltip
                  title="只关闭由本次任务启动且归 MAS 所有的目标进程，不会误杀用户手动打开的进程"
                >
                  <span class="form-label">
                    结束后关闭启动进程
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch
                v-model:checked="maafwConfig.Game.CloseOnFinish"
                checked-children="开启"
                un-checked-children="关闭"
                @change="emit('change', 'Game', 'CloseOnFinish', maafwConfig.Game.CloseOnFinish)"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-alert
          v-if="targetProcessMissing"
          class="control-strategy-alert target-process-alert"
          type="warning"
          show-icon
          message="请填写目标进程路径或目标进程名称"
          description="启动目标与检测目标是两套独立设置；当前模式保存前至少需要提供一个目标进程字段，MAS 才能等待并附加实际游戏。"
        />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ComboBoxItem } from '@/api'
import { isDirectControllerType, type EmulatorType } from '@/composables/useMaaFWScriptConfig'
import type {
  MaaFWControllerInfo,
  MaaFWInterfacePreviewData,
  MaaFWResourceInfo,
  MaaFWLaunchMode,
  MaaFWScriptConfig,
} from '@/types/script'

const props = defineProps<{
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  interfaceLoading: boolean
  emulatorLoading: boolean
  emulatorOptionsReady: boolean
  emulatorDeviceLoading: boolean
  emulatorOptions: ComboBoxItem[]
  emulatorDeviceOptions: ComboBoxItem[]
  emulatorTypeById: Record<string, EmulatorType>
  controllerOptions: MaaFWControllerInfo[]
  effectiveControllerName: string
  effectiveControllerType: string
  isAdbController: boolean
  isDesktopController: boolean
  resourceOptions: MaaFWResourceInfo[]
  unsupportedControllerOptions: MaaFWControllerInfo[]
  unsupportedControllerMessage: string
  adbControlStrategyMessage: string
  adbControlStrategyItems: Array<{ label: string; value: string }>
  selectedEmulatorLabel: string
  interfaceDependentDisabled: boolean
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'controller-change': []
  'resource-change': []
  'emulator-select-change': [emulatorId: string]
  'select-launch-path': []
}>()

const launchMode = computed<MaaFWLaunchMode>(() => props.maafwConfig.Game.LaunchMode)
const launchModeDescription = computed(() => {
  switch (launchMode.value) {
    case 'DirectExe':
      return '直接启动实际游戏 exe；目标进程字段用于后续附加与检测。'
    case 'LauncherExe':
      return '启动启动器 exe，再按目标进程字段等待并附加实际游戏。'
    case 'URL':
      return '交给系统协议处理器启动，再按目标进程字段等待并附加实际游戏。'
    default:
      return '不启动任何程序，只附加已经运行的目标进程。'
  }
})
const targetProcessMissing = computed(
  () =>
    launchMode.value !== 'DirectExe' &&
    !String(props.maafwConfig.Game.ProcessPath || '').trim() &&
    !String(props.maafwConfig.Game.ProcessName || '').trim()
)
</script>

<style scoped>
.form-section {
  margin-bottom: 40px;
}

.form-section-alt {
  margin: 0 -24px;
  padding: 24px 24px 32px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-text-quaternary);
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.modern-input {
  border-radius: 8px;
}

.field-help {
  margin-top: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  border: none;
  border-left: 1px solid var(--ant-color-border-secondary);
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
}

.controller-resource-row,
.control-detail-row {
  margin-top: 16px;
}

.control-strategy-alert {
  margin-bottom: 12px;
}

.target-process-alert {
  margin-top: 16px;
}

.control-strategy-summary {
  margin-top: 8px;
}

.control-fade-enter-active,
.control-fade-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.control-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.control-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
