<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <MaaFWFormSection :title="t('core.edit.controlConfiguration')" :icon="ControlOutlined">
    <!-- 模拟器的包名和等待时间之后，按注册顺序插入 besidePackageName 字段 -->
    <a-row :gutter="24" align="stretch" class="controller-resource-row">
      <a-col :xs="24" :md="12">
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
      <a-col :xs="24" :md="12">
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
        <a-col :xs="24" :md="12">
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
        <a-col :xs="24" :md="12">
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
        <!-- 插入点里每个组件各占一格（不叠在同一格里把旁边的策略表拉高）：页面传来组件数，每格用
             <slot> 转发一次并带上下标，页面渲染第 index 个组件 -->
        <a-col v-for="index in besideIndexes" :key="`beside-${index}`" :xs="24" :md="12">
          <slot name="besidePackageName" :index="index" />
        </a-col>
        <!-- 策略表：截图 / 输入两行，与同一行的表单项（标签 + 输入框）等高 -->
        <a-col :xs="24" :md="12" class="control-strategy-col">
          <MaaFWControlStrategyTable :items="adbControlStrategyItems" />
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
import type {
  MaaFWScriptControlSectionEmits,
  MaaFWScriptControlSectionProps,
} from '../../MaaFWFlavor/sectionContracts'
import MaaFWControlStrategyTable from './MaaFWControlStrategyTable.vue'
import MaaFWDesktopGameFields from './MaaFWDesktopGameFields.vue'
import MaaFWFormSection from './MaaFWFormSection.vue'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
const props = defineProps<MaaFWScriptControlSectionProps>()

const emit = defineEmits<MaaFWScriptControlSectionEmits>()

// 插入点 besidePackageName 各格的下标：组件数由页面按特调注册表传来（是 prop，变了 a-row 跟着更新）
const besideIndexes = computed(() =>
  Array.from({ length: props.besidePackageNameCount ?? 0 }, (_, index) => index)
)
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
.controller-resource-row {
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
