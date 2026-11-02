<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <MaaFWFormSection :title="t('core.edit.controlModeGameResource')">
    <!-- 模拟器依次排：控制方式、模拟器、实例、游戏资源、包名、等待时间、特调插槽
         besidePackageName、截图 / 输入策略表，格宽见脚本里的 adbCol。
         其余控制器这一行只有控制方式 | 游戏资源两格，各占半行 -->
    <a-row :gutter="24" align="stretch" class="controller-resource-row">
      <a-col v-bind="isAdbController ? adbCol('controller') : HALF_COL">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.controlMode') }}</span>
          </template>
          <a-select
            v-model:value="maafwConfig.Info.Controller"
            size="large"
            :placeholder="t('core.edit.automatic')"
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
                t('core.edit.originalUiRecommended')
              }}</span>
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <template v-if="isAdbController">
        <a-col v-bind="adbCol('emulator')">
          <a-form-item>
            <template #label>
              <span class="form-label">{{ t('core.edit.emulator') }}</span>
            </template>
            <a-select
              v-model:value="emulatorIdValue"
              size="large"
              :placeholder="t('core.edit.pickEmulator')"
              :loading="emulatorLoading"
              :disabled="!emulatorOptionsReady"
              @change="(value: string | number) => emit('emulator-select-change', String(value))"
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
        <a-col v-bind="adbCol('instance')">
          <a-form-item>
            <template #label>
              <span class="form-label">{{ t('core.edit.emulatorInstance') }}</span>
            </template>
            <a-input
              v-if="
                emulatorDeviceOptions.length === 0 &&
                !emulatorDeviceLoading &&
                maafwConfig.Emulator.Id &&
                maafwConfig.Emulator.Id !== '-'
              "
              v-model:value="emulatorIndexValue"
              size="large"
              :placeholder="t('core.edit.enterEmulatorInstanceIndex')"
              class="modern-input"
              :disabled="!emulatorOptionsReady"
              @blur="emit('change', 'Emulator', 'Index', maafwConfig.Emulator.Index)"
            />
            <a-select
              v-else
              v-model:value="emulatorIndexValue"
              size="large"
              :placeholder="t('core.edit.pickEmulatorFirst')"
              :loading="emulatorDeviceLoading"
              :disabled="
                !emulatorOptionsReady ||
                emulatorDeviceLoading ||
                !maafwConfig.Emulator.Id ||
                maafwConfig.Emulator.Id === '-'
              "
              @change="(value: string | number) => emit('change', 'Emulator', 'Index', value)"
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
      </template>
      <a-col v-bind="isAdbController ? adbCol('resource') : HALF_COL">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('core.edit.pickMfwResourceLeave')">
              <span class="form-label">
                {{ t('core.edit.gameResource') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Info.Resource"
            size="large"
            :placeholder="t('core.edit.automatic')"
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
      <template v-if="isAdbController">
        <a-col v-bind="adbCol('packageName')">
          <a-form-item>
            <template #label>
              <a-tooltip :title="t('core.edit.mfwGamePackageNamePassed')">
                <span class="form-label">
                  {{ t('core.edit.mfwGamePackageName') }}
                  <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="maafwConfig.Game.PackageName"
              :placeholder="t('core.edit.mfwGamePackageNamePlaceholder')"
              size="large"
              allow-clear
              @blur="emit('change', 'Game', 'PackageName', maafwConfig.Game.PackageName)"
            />
          </a-form-item>
        </a-col>
        <a-col v-bind="adbCol('waitTime')">
          <a-form-item>
            <template #label>
              <a-tooltip :title="t('core.edit.mfwWaitTimeTip')">
                <span class="form-label">
                  {{ t('core.edit.waitTimeSeconds') }}
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
        <a-col v-if="$slots.besidePackageName" v-bind="adbCol('beside')">
          <slot name="besidePackageName" />
        </a-col>
        <!-- 策略表：截图 / 输入两行，与同一行的表单项（标签 + 输入框）等高 -->
        <a-col v-bind="adbCol('strategy')" class="control-strategy-col">
          <MaaFWControlStrategyTable :items="adbControlStrategyItems" />
        </a-col>
      </template>
    </a-row>

    <Transition name="control-fade" mode="out-in">
      <div v-if="isDesktopController" key="win32">
        <!-- 两行摆完：启动方式 | 游戏 exe ；Unity 分辨率 | 启动参数 | 等待时间 | 键位映射 -->
        <a-row :gutter="24" class="control-detail-row">
          <a-col :span="12">
            <a-form-item>
              <template #label>
                <span class="form-label">{{ t('core.edit.howPcGameLaunched') }}</span>
              </template>
              <!-- 收起时只显示标题（option-label-prop），说明只在展开的选项里出现 -->
              <a-select
                v-model:value="maafwConfig.Game.LaunchMode"
                size="large"
                style="width: 100%"
                option-label-prop="label"
                @change="emit('change', 'Game', 'LaunchMode', maafwConfig.Game.LaunchMode)"
              >
                <a-select-option value="DirectExe" :label="t('core.edit.letMasLaunchGame')">
                  <div class="launch-option">
                    <span class="launch-option-title">{{ t('core.edit.letMasLaunchGame') }}</span>
                    <span class="launch-option-hint">{{ t('core.edit.pickGameSOwn') }}</span>
                  </div>
                </a-select-option>
                <a-select-option value="AttachOnly" :label="t('core.edit.launchGameOtherWay')">
                  <div class="launch-option">
                    <span class="launch-option-title">{{ t('core.edit.launchGameOtherWay') }}</span>
                    <span class="launch-option-hint">{{ t('core.edit.masOnlyTakesOver') }}</span>
                  </div>
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col v-if="launchMode === 'DirectExe'" :span="12">
            <a-form-item>
              <template #label>
                <span class="form-label">{{ t('core.edit.gameExecutable') }}</span>
              </template>
              <PathPickerField
                v-model="maafwConfig.Game.LaunchPath"
                mode="file"
                :placeholder="t('core.edit.pickGameExeThat')"
                :pick-label="t('core.edit.pickExe')"
                @pick="emit('select-launch-path')"
              />
            </a-form-item>
          </a-col>
          <!-- 由脚本自身控制游戏时第二行整行隐藏，键位映射挪到启动方式右边 -->
          <MaaFWHotkeyField
            v-if="launchMode !== 'DirectExe'"
            :script-id="scriptId"
            :preview-data="previewData"
            :controller-name="effectiveControllerName"
            :resource-name="effectiveResourceName"
            :value="maafwConfig.Game.Hotkeys"
            @save="handleHotkeysSave"
          />
        </a-row>

        <a-row v-if="launchMode === 'DirectExe'" :gutter="24" class="control-detail-row">
          <a-col :span="directExeColSpan">
            <a-form-item>
              <template #label>
                <a-tooltip :title="t('core.edit.mfwUnityResolutionTip')">
                  <span class="form-label">
                    {{ t('core.edit.mfwUnityResolution') }}
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
          <a-col :span="directExeColSpan">
            <a-form-item>
              <template #label>
                <span class="form-label">{{ t('core.edit.launchArguments') }}</span>
              </template>
              <a-input
                v-model:value="maafwConfig.Game.Arguments"
                :placeholder="t('core.edit.optional')"
                size="large"
                class="modern-input"
                @blur="emit('change', 'Game', 'Arguments', maafwConfig.Game.Arguments)"
              />
            </a-form-item>
          </a-col>
          <a-col :span="directExeColSpan">
            <a-form-item>
              <template #label>
                <a-tooltip :title="t('core.edit.mfwWaitTimeTip')">
                  <span class="form-label">
                    {{ t('core.edit.waitTimeSeconds') }}
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
          <MaaFWHotkeyField
            v-if="launchMode === 'DirectExe'"
            :script-id="scriptId"
            :preview-data="previewData"
            :controller-name="effectiveControllerName"
            :resource-name="effectiveResourceName"
            :value="maafwConfig.Game.Hotkeys"
            @save="handleHotkeysSave"
          />
        </a-row>
      </div>
    </Transition>
  </MaaFWFormSection>
</template>

<script setup lang="ts">
import PathPickerField from '@/components/PathPickerField.vue'
import { useI18n } from 'vue-i18n'
import { computed, useSlots } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { isDirectControllerType } from '@/composables/useMaaFWScriptConfig'
import type { MaaFWLaunchMode, MaaFWUnityResolution } from '@/types/script'
import type {
  MaaFWScriptControlSectionEmits,
  MaaFWScriptControlSectionProps,
} from '../../MaaFWFlavor/sectionContracts'
import MaaFWControlStrategyTable from './MaaFWControlStrategyTable.vue'
import MaaFWFormSection from './MaaFWFormSection.vue'
import MaaFWHotkeyField from './MaaFWHotkeyField.vue'
import { collectHotkeyOptions } from './hotkeyOptions'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
const props = defineProps<MaaFWScriptControlSectionProps>()

const emit = defineEmits<MaaFWScriptControlSectionEmits>()

const launchMode = computed<MaaFWLaunchMode>(() => props.maafwConfig.Game.LaunchMode)

const slots = useSlots()

const HALF_COL = { span: 12 } as const

// 宽屏每行最多三格，最后一行不留单格：余两格时最后一行两格（8 格 = 3 / 3 / 2），余一格时
// 最后两行各两格（7 格 = 3 / 2 / 2）。返回每格的栅格宽度
const wideRowSpans = (count: number): number[] => {
  const rows: number[] = []
  let rest = count
  while (rest > 0) {
    const size = rest === 4 ? 2 : Math.min(rest, 3)
    rows.push(size)
    rest -= size
  }
  return rows.flatMap(size => Array<number>(size).fill(24 / size))
}

type AdbField =
  | 'controller'
  | 'emulator'
  | 'instance'
  | 'resource'
  | 'packageName'
  | 'waitTime'
  | 'beside'
  | 'strategy'

// 模拟器各格按模板顺序排；插槽不是响应式的，写成函数在渲染时取
const adbFields = (): AdbField[] => [
  'controller',
  'emulator',
  'instance',
  'resource',
  'packageName',
  'waitTime',
  ...(slots.besidePackageName ? (['beside'] as const) : []),
  'strategy',
]

// 中等宽度两列、窄屏一列，宽屏按 wideRowSpans
const adbCol = (field: AdbField) => {
  const fields = adbFields()
  return { xs: 24, md: 12, xl: wideRowSpans(fields.length)[fields.indexOf(field)] }
}

// 模拟器 / 实例下拉的「未选择」（值为 -）由后端列表自带，这里不再另加一项。列表还没到时
// （加载中、加载失败、没选模拟器时实例列表为空）选项里没有它，框里会直接露出「-」，改显示占位文字；
// 扫不到实例改手动输入时同理
const shownWhenListed = (value: string, options: Array<{ value: string | null }>) =>
  value === '-' && !options.some(item => item.value === '-') ? undefined : value

const emulatorIdValue = computed({
  get: () => shownWhenListed(props.maafwConfig.Emulator.Id, props.emulatorOptions),
  set: (value: string | undefined) => {
    props.maafwConfig.Emulator.Id = value ?? '-'
  },
})

const emulatorIndexValue = computed({
  get: () => shownWhenListed(props.maafwConfig.Emulator.Index, props.emulatorDeviceOptions),
  set: (value: string | undefined) => {
    props.maafwConfig.Emulator.Index = value ?? '-'
  },
})

// 「让 MAS 启动游戏」的第二行：键位映射格只在 interface 有对当前控制器 / 资源生效的 hotkey option
// 时才渲染（与 MaaFWHotkeyField 同一判据），没有它时其余三格各占三分之一，不在右边空出一格
const hasHotkeyField = computed(
  () =>
    collectHotkeyOptions(
      props.previewData,
      props.effectiveControllerName,
      props.effectiveResourceName
    ).length > 0
)
const directExeColSpan = computed(() => (hasHotkeyField.value ? 6 : 8))

// 键位映射弹窗保存：先改草稿再走页面的自动保存通道
const handleHotkeysSave = (value: string) => {
  props.maafwConfig.Game.Hotkeys = value
  emit('change', 'Game', 'Hotkeys', value)
}

// 只给两档常用尺寸：Unity 播放器只认整数宽高，1080p 是各脚本闸门的基准，720p 留给小屏
const unityResolutionOptions = computed<Array<{ label: string; value: MaaFWUnityResolution }>>(
  () => [
    { label: t('core.edit.mfwUnityResolutionOff'), value: 'Off' },
    { label: '1920×1080', value: '1920x1080' },
    { label: '1280×720', value: '1280x720' },
  ]
)
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
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

.controller-resource-row,
.control-detail-row {
  margin-top: 16px;
}

/* 行是 align=stretch，策略表所在列被拉到与同一行表单项等高（标签 + 输入框 + 底距）；列做成 flex，
   表格组件在里面撑满列高。窄屏独占一行时按内容高度 */
.control-strategy-col {
  display: flex;
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
