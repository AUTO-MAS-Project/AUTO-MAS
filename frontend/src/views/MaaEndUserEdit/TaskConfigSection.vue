<!-- eslint-disable vue/no-v-html -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>任务配置</h3>
      <a-button
        v-if="
          isPlanMode &&
          formData.Info.ProtocolSpaceMode &&
          formData.Info.ProtocolSpaceMode !== 'Fixed'
        "
        type="link"
        class="plans-button"
        @click="handleGoToPlans"
      >
        <template #icon>
          <CalendarOutlined />
        </template>
        跳转到计划表
      </a-button>
    </div>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip title="可选择固定配置或引用 MaaEnd 计划表">
              <span class="form-label">
                协议空间配置模式
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.ProtocolSpaceMode"
            :options="protocolSpaceModeOptions"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.ProtocolSpaceMode', formData.Info.ProtocolSpaceMode)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip
              :title="
                isPlanMode ? '当前生效的协议空间分类来自计划表' : '选择当前要执行的协议空间任务分类'
              "
            >
              <span class="form-label">
                协议空间
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displayProtocolSpace }}</div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(protocolSpaceTooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <a-select
            v-else
            v-model:value="formData.Task.ProtocolSpaceTab"
            :options="PROTOCOL_SPACE_OPTIONS"
            :disabled="loading"
            size="large"
            @change="handleProtocolSpaceChange"
          />
        </a-form-item>
      </a-col>

      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="isPlanMode ? '当前生效任务来自计划表' : taskOptionTooltip">
              <span class="form-label">
                {{ taskOptionLabel }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displayCurrentTask }}</div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(currentTaskTooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <a-select
            v-else
            v-model:value="currentTaskValue"
            :options="currentTaskOptions"
            :disabled="loading"
            size="large"
            @change="handleTaskOptionChange"
          />
        </a-form-item>
      </a-col>

      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip
              :title="
                isPlanMode
                  ? '当前生效奖励组来自计划表；非奖励型任务会固定为奖励组 A'
                  : '当前任务支持奖励组切换时，可在这里选择对应奖励组'
              "
            >
              <span class="form-label">
                可选奖励组
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displayRewardsSet }}</div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(rewardsTooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <a-select
            v-else
            v-model:value="formData.Task.RewardsSetOption"
            :options="REWARD_OPTIONS"
            :disabled="loading || !rewardGroupEnabled"
            size="large"
            @change="emitSave('Task.RewardsSetOption', formData.Task.RewardsSetOption)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { CalendarOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { navigateTo } from '@/router'
import {
  PROTOCOL_SPACE_OPTIONS,
  PROTOCOL_SPACE_LABEL_MAP,
  PROTOCOL_SPACE_TASK_FIELD_MAP,
  PROTOCOL_SPACE_TASK_LABEL_MAP,
  PROTOCOL_SPACE_TASK_OPTIONS_MAP,
  PROTOCOL_SPACE_TASK_TITLE_MAP,
  PROTOCOL_SPACE_TASK_TOOLTIP_MAP,
  REWARD_LABEL_MAP,
  REWARD_OPTIONS,
  getCurrentProtocolTaskValue,
  normalizeProtocolSpaceConfig,
  type ProtocolSpaceConfig,
  type ProtocolSpaceTab,
} from '@/utils/maaEndProtocolSpace'

const props = defineProps<{
  formData: any
  loading: boolean
  isPlanMode: boolean
  protocolSpaceModeOptions: Array<{ label: string; value: string }>
  planModeConfig: ProtocolSpaceConfig | null
  protocolSpaceTooltip: string
  currentTaskTooltip: string
  rewardsTooltip: string
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const formData = props.formData

const currentField = computed(
  () =>
    PROTOCOL_SPACE_TASK_FIELD_MAP[
      (formData.Task.ProtocolSpaceTab ?? 'OperatorProgression') as ProtocolSpaceTab
    ]
)

const currentTaskOptions = computed(
  () =>
    PROTOCOL_SPACE_TASK_OPTIONS_MAP[
      (formData.Task.ProtocolSpaceTab ?? 'OperatorProgression') as ProtocolSpaceTab
    ] ?? PROTOCOL_SPACE_TASK_OPTIONS_MAP.OperatorProgression
)

const currentTaskValue = computed({
  get: () => formData.Task[currentField.value],
  set: value => {
    formData.Task[currentField.value] = value
  },
})

const currentTaskOption = computed(() =>
  currentTaskOptions.value.find(option => option.value === currentTaskValue.value)
)

const rewardGroupEnabled = computed(() => Boolean(currentTaskOption.value?.rewards))

const displayPlanConfig = computed(() =>
  props.planModeConfig ? normalizeProtocolSpaceConfig(props.planModeConfig) : null
)

const displayProtocolSpace = computed(() => {
  if (!displayPlanConfig.value) return '未读取到计划表配置'
  return PROTOCOL_SPACE_LABEL_MAP[displayPlanConfig.value.ProtocolSpaceTab]
})

const displayCurrentTask = computed(() => {
  if (!displayPlanConfig.value) return '未读取到计划表配置'
  return PROTOCOL_SPACE_TASK_LABEL_MAP[getCurrentProtocolTaskValue(displayPlanConfig.value)]
})

const displayRewardsSet = computed(() => {
  if (!displayPlanConfig.value) return '未读取到计划表配置'
  return REWARD_LABEL_MAP[displayPlanConfig.value.RewardsSetOption]
})

const displayProtocolSpaceTab = computed<ProtocolSpaceTab>(() => {
  if (props.isPlanMode && displayPlanConfig.value) {
    return displayPlanConfig.value.ProtocolSpaceTab
  }

  return (formData.Task.ProtocolSpaceTab ?? 'OperatorProgression') as ProtocolSpaceTab
})

const taskOptionLabel = computed(
  () => PROTOCOL_SPACE_TASK_TITLE_MAP[displayProtocolSpaceTab.value] ?? '协议空间任务'
)

const taskOptionTooltip = computed(
  () => PROTOCOL_SPACE_TASK_TOOLTIP_MAP[displayProtocolSpaceTab.value] ?? '选择当前协议空间任务'
)

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const handleGoToPlans = () => {
  const planId =
    props.isPlanMode &&
    formData.Info.ProtocolSpaceMode &&
    formData.Info.ProtocolSpaceMode !== 'Fixed'
      ? formData.Info.ProtocolSpaceMode
      : undefined

  navigateTo('/plans', {
    query: {
      from: 'protocol-space-config',
      ...(planId ? { planId } : {}),
    },
  })
}

const ensureCurrentTaskValue = () => {
  const options = currentTaskOptions.value
  if (!options.some(option => option.value === currentTaskValue.value)) {
    currentTaskValue.value = options[0].value
  }
}

const ensureRewardGroupState = () => {
  if (!rewardGroupEnabled.value && formData.Task.RewardsSetOption !== 'RewardsSetA') {
    formData.Task.RewardsSetOption = 'RewardsSetA'
    emitSave('Task.RewardsSetOption', formData.Task.RewardsSetOption)
  }
}

const handleProtocolSpaceChange = () => {
  ensureCurrentTaskValue()
  emitSave('Task.ProtocolSpaceTab', formData.Task.ProtocolSpaceTab)
  emitSave(`Task.${currentField.value}`, currentTaskValue.value)
  ensureRewardGroupState()
}

const handleTaskOptionChange = () => {
  emitSave(`Task.${currentField.value}`, currentTaskValue.value)
  ensureRewardGroupState()
}

const escapeHtml = (text: string) =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const formatTooltip = (text: string) => (text ? escapeHtml(text).replace(/\n/g, '<br/>') : '')

watch(
  () => formData.Task.ProtocolSpaceTab,
  () => {
    if (props.isPlanMode) return
    ensureCurrentTaskValue()
    ensureRewardGroupState()
  },
  { immediate: true }
)
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
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

.plans-button {
  font-size: 14px;
  color: var(--ant-color-primary);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.plan-mode-display {
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.plan-value {
  font-size: 14px;
  color: var(--ant-color-text);
  font-weight: 500;
  flex: 1;
}

.plan-source {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--ant-color-primary);
  cursor: help;
}

.plan-tooltip {
  max-width: 360px;
  line-height: 1.6;
  white-space: normal;
}
</style>
