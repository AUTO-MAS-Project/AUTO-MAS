<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <MaaFWFormSection :title="t('core.edit.controlConfiguration')" :icon="ControlOutlined">
    <template v-if="gameBinding.available" #actions>
      <router-link to="/games" class="manage-link">
        {{ t('core.games.manageTargets') }} →
      </router-link>
    </template>
    <slot name="notice" />
    <a-alert
      v-if="gameBinding.error"
      type="error"
      :message="gameBinding.error"
      show-icon
      class="binding-alert"
    >
      <template #action>
        <a-button size="small" @click="gameBinding.reload">{{ t('core.games.retry') }}</a-button>
      </template>
    </a-alert>
    <a-alert
      v-if="gameBinding.warning"
      type="warning"
      :message="gameBinding.warning"
      show-icon
      class="binding-alert"
    >
      <template v-if="gameBinding.canClear" #action>
        <a-button size="small" :disabled="gameBinding.disabled" @click="gameBinding.resetBinding">
          {{ t('core.edit.clear') }}
        </a-button>
      </template>
    </a-alert>
    <!-- 模拟器依次排：控制方式、模拟器、实例、游戏资源、包名、等待时间、专属页的 besidePackageName
         （每个字段一格）、截图 / 输入策略表；桌面端这一行只有控制方式 | 游戏资源，其余在下面；
         「自动」时是控制方式 | 游戏资源 | 目标 | 设备。格宽见 controlGrid.ts -->
    <a-row :gutter="24" align="stretch" class="controller-resource-row">
      <a-col v-bind="col('controller')">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.controlMode') }}</span>
          </template>
          <a-select
            v-model:value="maafwConfig.Info.Controller"
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
      <template v-if="isAdbController && gameBinding.available">
        <a-col v-bind="col('target')">
          <MaaFWGameTargetSelect
            :binding="gameBinding"
            :label="t('core.edit.emulator')"
            :placeholder="t('core.edit.pickEmulator')"
          />
        </a-col>
        <a-col v-bind="col('device')">
          <MaaFWGameDeviceSelect
            :binding="gameBinding"
            :label="t('core.edit.emulatorInstance')"
            :empty-placeholder="t('core.edit.pickEmulatorFirst')"
          />
        </a-col>
      </template>
      <a-col v-bind="col('resource')">
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
        <a-col v-bind="col('packageName')">
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
              allow-clear
              @blur="emit('change', 'Game', 'PackageName', maafwConfig.Game.PackageName)"
            />
          </a-form-item>
        </a-col>
        <a-col v-bind="col('waitTime')">
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
              style="width: 100%"
              @blur="emit('change', 'Game', 'WaitTime', maafwConfig.Game.WaitTime)"
            />
          </a-form-item>
        </a-col>
        <!-- 专属页的字段每个各占一格（不叠在同一格里把旁边的策略表拉高）：页面传来格数，每格用
             <slot> 转发一次并带上下标，页面渲染第 index 格 -->
        <a-col
          v-for="index in besideIndexes"
          :key="`beside-${index}`"
          v-bind="col(`beside${index}`)"
        >
          <slot name="besidePackageName" :index="index" />
        </a-col>
        <!-- 策略表：截图 / 输入两行，与同一行的表单项（标签 + 输入框）等高 -->
        <a-col v-bind="col('strategy')" class="control-strategy-col">
          <MaaFWControlStrategyTable :items="adbControlStrategyItems" />
        </a-col>
      </template>
      <template v-if="isAutoController && gameBinding.available">
        <a-col v-bind="col('target')">
          <MaaFWGameTargetSelect
            :binding="gameBinding"
            :label="t('core.games.target')"
            :placeholder="t('core.games.selectTarget')"
          />
        </a-col>
        <a-col v-bind="col('device')">
          <MaaFWGameDeviceSelect
            :binding="gameBinding"
            :label="t('core.games.device')"
            :empty-placeholder="t('core.games.selectTarget')"
          />
        </a-col>
      </template>
    </a-row>

    <Transition name="control-fade" mode="out-in">
      <MaaFWDesktopGameFields
        v-if="isDesktopController"
        key="win32"
        :script-id="scriptId"
        :maafw-config="maafwConfig"
        :preview-data="previewData"
        :effective-controller-name="effectiveControllerName"
        :effective-resource-name="effectiveResourceName"
        :game-binding="gameBinding"
        @change="(category, key, value) => emit('change', category, key, value)"
        @select-launch-path="emit('select-launch-path')"
        @select-launcher-path="emit('select-launcher-path')"
      />
    </Transition>
  </MaaFWFormSection>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { ControlOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { isDirectControllerType } from '@/composables/useMaaFWScriptConfig'
import type { MaaFWScriptControlSectionEmits, MaaFWScriptControlSectionProps } from './sectionProps'
import MaaFWControlStrategyTable from './MaaFWControlStrategyTable.vue'
import MaaFWDesktopGameFields from './MaaFWDesktopGameFields.vue'
import MaaFWFormSection from './MaaFWFormSection.vue'
import MaaFWGameDeviceSelect from './MaaFWGameDeviceSelect.vue'
import MaaFWGameTargetSelect from './MaaFWGameTargetSelect.vue'
import { fieldCols } from './controlGrid'
import { useMaaFWInlineGameBinding } from './useMaaFWInlineGameBinding'

const { t } = useI18n()

// props / 事件见 sectionProps.ts
const props = defineProps<MaaFWScriptControlSectionProps>()

const emit = defineEmits<MaaFWScriptControlSectionEmits>()

// 模拟器 / 客户端与设备直接写托管的游戏绑定（游戏管理是唯一来源），切换控制方式时不清空，
// 类型不符就地提示、可手动清空
const gameBinding = useMaaFWInlineGameBinding(
  () => props.scriptId,
  () => props.effectiveControllerType
)

const isAutoController = computed(() => !props.isAdbController && !props.isDesktopController)

// besidePackageName 各格的下标：格数由页面传来（是 prop，变了 a-row 跟着更新）
const besideIndexes = computed(() =>
  Array.from({ length: props.besidePackageNameCount ?? 0 }, (_, index) => index)
)

type ControlField =
  | 'controller'
  | 'target'
  | 'device'
  | 'resource'
  | 'packageName'
  | 'waitTime'
  | `beside${number}`
  | 'strategy'

// 这一行的格按控制方式排，格宽由格数决定（controlGrid.ts）
const fields = computed<ControlField[]>(() => {
  const binding: ControlField[] = gameBinding.available ? ['target', 'device'] : []
  if (props.isAdbController) {
    return [
      'controller',
      ...binding,
      'resource',
      'packageName',
      'waitTime',
      ...besideIndexes.value.map((index): ControlField => `beside${index}`),
      'strategy',
    ]
  }
  if (props.isDesktopController) return ['controller', 'resource']
  return ['controller', 'resource', ...binding]
})
const col = computed(() => fieldCols(fields.value))
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
.controller-resource-row {
  margin-top: 16px;
}

/* 与专属页 notice 里的提示同一间距 */
.binding-alert {
  margin-bottom: 16px;
}

.manage-link {
  font-size: 13px;
  color: var(--ant-color-link);
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
