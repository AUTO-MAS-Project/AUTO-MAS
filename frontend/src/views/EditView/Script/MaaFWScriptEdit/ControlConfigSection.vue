<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section form-section-alt">
    <div class="section-header">
      <h3>{{ t('edit.controlModeGameResource') }}</h3>
    </div>

    <a-row :gutter="24" class="controller-resource-row">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.pickMfwControllerThat')">
              <span class="form-label">
                {{ t('edit.controlMode') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Info.Controller"
            size="large"
            :placeholder="t('edit.automatic')"
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
              <span v-if="!isDirectControllerType(item.type)">{{
                t('edit.originalUiRecommended')
              }}</span>
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.pickMfwResourceLeave')">
              <span class="form-label">
                {{ t('edit.gameResource') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Info.Resource"
            size="large"
            :placeholder="t('edit.automatic')"
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
                <a-tooltip :title="t('edit.mfwAdbControllerUses')">
                  <span class="form-label">
                    {{ t('edit.emulator') }}
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="maafwConfig.Emulator.Id"
                size="large"
                :placeholder="t('edit.pickEmulator')"
                :loading="emulatorLoading"
                :disabled="!emulatorOptionsReady"
                @change="(value: string | number) => emit('emulator-select-change', String(value))"
              >
                <a-select-option value="-">{{ t('edit.unspecified') }}</a-select-option>
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
                <a-tooltip :title="t('edit.pickEmulatorInstancePassed')">
                  <span class="form-label">
                    {{ t('edit.emulatorInstance') }}
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
                :placeholder="t('edit.enterEmulatorInstanceIndex')"
                class="modern-input"
                :disabled="!emulatorOptionsReady"
                @blur="emit('change', 'Emulator', 'Index', maafwConfig.Emulator.Index)"
              />
              <a-select
                v-else
                v-model:value="maafwConfig.Emulator.Index"
                size="large"
                :placeholder="t('edit.pickEmulatorFirst')"
                :loading="emulatorDeviceLoading"
                :disabled="
                  !emulatorOptionsReady ||
                  emulatorDeviceLoading ||
                  !maafwConfig.Emulator.Id ||
                  maafwConfig.Emulator.Id === '-'
                "
                @change="(value: string | number) => emit('change', 'Emulator', 'Index', value)"
              >
                <a-select-option value="-">{{ t('edit.unspecified') }}</a-select-option>
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
          :message="t('edit.win32ControlMethodCan')"
        />

        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('edit.howPcGameLaunched') }}</span>
          </template>
          <a-select
            v-model:value="maafwConfig.Game.LaunchMode"
            size="large"
            style="width: 100%"
            @change="emit('change', 'Game', 'LaunchMode', maafwConfig.Game.LaunchMode)"
          >
            <a-select-option value="AttachOnly">
              <div class="launch-option">
                <span class="launch-option-title">{{ t('edit.iLaunchGameMyself') }}</span>
                <span class="launch-option-hint">{{ t('edit.masOnlyTakesOver') }}</span>
              </div>
            </a-select-option>
            <a-select-option value="DirectExe">
              <div class="launch-option">
                <span class="launch-option-title">{{ t('edit.letMasLaunchGame') }}</span>
                <span class="launch-option-hint">{{ t('edit.pickGameSOwn') }}</span>
              </div>
            </a-select-option>
          </a-select>
          <div class="field-help">{{ launchModeDescription }}</div>
        </a-form-item>

        <a-row v-if="launchMode === 'DirectExe'" :gutter="24" class="control-detail-row">
          <a-col :span="12">
            <a-form-item>
              <template #label>
                <a-tooltip :title="t('edit.actualGameExeMas')">
                  <span class="form-label">
                    {{ t('edit.gameExecutable') }}
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-group compact class="path-input-group">
                <a-input
                  v-model:value="maafwConfig.Game.LaunchPath"
                  :placeholder="t('edit.pickGameExeThat')"
                  size="large"
                  class="path-input"
                  readonly
                />
                <a-button size="large" class="path-button" @click="emit('select-launch-path')">
                  <template #icon>
                    <FolderOpenOutlined />
                  </template>
                  {{ t('edit.pickExe') }}
                </a-button>
              </a-input-group>
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item>
              <template #label>
                <a-tooltip :title="t('edit.commandLineArgumentsPassed')">
                  <span class="form-label">
                    {{ t('edit.launchArguments') }}
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="maafwConfig.Game.Arguments"
                :placeholder="t('edit.optional')"
                size="large"
                class="modern-input"
                @blur="emit('change', 'Game', 'Arguments', maafwConfig.Game.Arguments)"
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item>
              <template #label>
                <a-tooltip :title="t('edit.howLongWaitReal')">
                  <span class="form-label">
                    {{ t('edit.waitTime') }}
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

        <a-row v-if="launchMode === 'DirectExe'" :gutter="24" class="control-detail-row">
          <a-col :span="12">
            <a-form-item>
              <template #label>
                <a-tooltip :title="t('edit.onlyProcessesStartedBy')">
                  <span class="form-label">
                    {{ t('edit.closeLaunchedProcessAfterwards') }}
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-switch
                v-model:checked="maafwConfig.Game.CloseOnFinish"
                :checked-children="t('edit.on2')"
                :un-checked-children="t('edit.off')"
                @change="emit('change', 'Game', 'CloseOnFinish', maafwConfig.Game.CloseOnFinish)"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
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

const { t } = useI18n()

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
      return 'MAS 会启动你选的游戏 exe，运行结束后按下方设置决定是否关闭它。'
    default:
      return 'MAS 不会启动任何程序，只等你把游戏开起来后接管它。'
  }
})
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

.launch-option {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
  padding: 2px 0;
}

.launch-option-title {
  font-weight: 500;
}

.launch-option-hint {
  font-size: 12px;
  opacity: 0.65;
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
