<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.controlModeGameResource') }}</h3>
    </div>

    <a-row :gutter="24" class="controller-resource-row">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('edit.controlMode') }}</span>
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

    <Transition name="control-fade" mode="out-in">
      <div v-if="isAdbController" key="adb">
        <a-row :gutter="24" class="control-detail-row">
          <a-col :span="12">
            <a-form-item>
              <template #label>
                <span class="form-label">{{ t('edit.emulator') }}</span>
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
                <span class="form-label">{{ t('edit.emulatorInstance') }}</span>
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

        <!-- type=flex + stretch：右边的策略表跟左边「标签 + 输入框」等高，上下边对齐 -->
        <a-row :gutter="24" type="flex" align="stretch" class="control-detail-row">
          <a-col :span="12">
            <a-form-item>
              <template #label>
                <a-tooltip :title="t('edit.mfwGamePackageNamePassed')">
                  <span class="form-label">
                    {{ t('edit.mfwGamePackageName') }}
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="maafwConfig.Game.PackageName"
                :placeholder="t('edit.mfwGamePackageNamePlaceholder')"
                allow-clear
                @blur="emit('change', 'Game', 'PackageName', maafwConfig.Game.PackageName)"
              />
            </a-form-item>
          </a-col>
          <!-- 控制策略表放在包名右边：截图 / 输入两行，撑满整列高度 -->
          <a-col :span="12" class="control-strategy-col">
            <a-descriptions :column="1" size="small" bordered class="control-strategy-summary">
              <a-descriptions-item
                v-for="item in adbControlStrategyItems"
                :key="item.label"
                :label="item.label"
              >
                {{ item.value }}
              </a-descriptions-item>
            </a-descriptions>
          </a-col>
        </a-row>
      </div>

      <div v-else-if="isDesktopController" key="win32">
        <!-- 两行摆完：启动方式 | 游戏 exe ；Unity 分辨率 | 启动参数 | 等待时间 | 启动后再等 -->
        <a-row :gutter="24" class="control-detail-row">
          <a-col :span="12">
            <a-form-item>
              <template #label>
                <span class="form-label">{{ t('edit.howPcGameLaunched') }}</span>
              </template>
              <!-- 收起时只显示标题（option-label-prop），说明只在展开的选项里出现 -->
              <a-select
                v-model:value="maafwConfig.Game.LaunchMode"
                size="large"
                style="width: 100%"
                option-label-prop="label"
                @change="emit('change', 'Game', 'LaunchMode', maafwConfig.Game.LaunchMode)"
              >
                <a-select-option value="DirectExe" :label="t('edit.letMasLaunchGame')">
                  <div class="launch-option">
                    <span class="launch-option-title">{{ t('edit.letMasLaunchGame') }}</span>
                    <span class="launch-option-hint">{{ t('edit.pickGameSOwn') }}</span>
                  </div>
                </a-select-option>
                <a-select-option value="AttachOnly" :label="t('edit.launchGameOtherWay')">
                  <div class="launch-option">
                    <span class="launch-option-title">{{ t('edit.launchGameOtherWay') }}</span>
                    <span class="launch-option-hint">{{ t('edit.masOnlyTakesOver') }}</span>
                  </div>
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col v-if="launchMode === 'DirectExe'" :span="12">
            <a-form-item>
              <template #label>
                <span class="form-label">{{ t('edit.gameExecutable') }}</span>
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
        </a-row>

        <a-row v-if="launchMode === 'DirectExe'" :gutter="24" class="control-detail-row">
          <a-col :span="6">
            <a-form-item>
              <template #label>
                <a-tooltip :title="t('edit.mfwUnityResolutionTip')">
                  <span class="form-label">
                    {{ t('edit.mfwUnityResolution') }}
                    <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="maafwConfig.Game.UnityResolution"
                size="large"
                style="width: 100%"
                :options="unityResolutionOptions"
                @change="
                  (value: string | number) => emit('change', 'Game', 'UnityResolution', value)
                "
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item>
              <template #label>
                <span class="form-label">{{ t('edit.launchArguments') }}</span>
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
                <a-tooltip :title="t('edit.mfwWaitTimeTip')">
                  <span class="form-label">
                    {{ t('edit.waitTimeSeconds') }}
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
  MaaFWUnityResolution,
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

// 只给两档常用尺寸：Unity 播放器只认整数宽高，1080p 是各脚本闸门的基准，720p 留给小屏
const unityResolutionOptions = computed<Array<{ label: string; value: MaaFWUnityResolution }>>(
  () => [
    { label: t('edit.mfwUnityResolutionOff'), value: 'Off' },
    { label: '1920×1080', value: '1920x1080' },
    { label: '1280×720', value: '1280x720' },
  ]
)
</script>

<style scoped>
.form-section {
  margin-bottom: 40px;
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

/* 右列整体是 flex，表格撑满列高（列高 = 左边 a-form-item 的标签 + 输入框 + 底距），再减去
   与 a-form-item 相同的底距（本项目全局把它定成 20px），上下边就与左边对齐；两行均分高度 */
.control-strategy-col {
  display: flex;
}

.control-strategy-summary {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  margin-bottom: 20px;
}

/* view 也做成 flex 列，表格作为 flex 项被拉到满高（height:100% 在这里解析不出来，差 3px） */
.control-strategy-summary :deep(.ant-descriptions-view) {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.control-strategy-summary :deep(.ant-descriptions-view table) {
  flex: 1;
}

.control-strategy-summary :deep(.ant-descriptions-item-label),
.control-strategy-summary :deep(.ant-descriptions-item-content) {
  padding: 4px 12px !important;
  font-size: 13px;
}

.control-strategy-summary :deep(.ant-descriptions-item-label) {
  width: 28%;
  color: var(--ant-color-text-secondary);
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
