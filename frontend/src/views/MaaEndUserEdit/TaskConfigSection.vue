<!-- eslint-disable vue/no-mutating-props -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>任务配置</h3>
    </div>

    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="选择当前要执行的协议空间任务分类">
              <span class="form-label">
                协议空间
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Task.ProtocolSpaceTab"
            :options="protocolSpaceOptions"
            size="large"
            @change="handleProtocolSpaceChange"
          />
        </a-form-item>
      </a-col>

      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="taskOptionTooltip">
              <span class="form-label">
                {{ taskOptionLabel }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="currentTaskValue"
            :options="currentTaskOptions"
            size="large"
            @change="handleTaskOptionChange"
          />
        </a-form-item>
      </a-col>

      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="当前任务支持奖励组切换时，可在这里选择对应奖励组">
              <span class="form-label">
                可选奖励组
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Task.RewardsSetOption"
            :options="rewardOptions"
            :disabled="!rewardGroupEnabled"
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
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const props = defineProps<{
  formData: any
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const protocolSpaceOptions = [
  { label: '干员养成', value: 'OperatorProgression' },
  { label: '武器养成', value: 'WeaponProgression' },
  { label: '危境预演', value: 'CrisisDrills' },
]

const taskOptionsMap: Record<string, Array<{ label: string; value: string; rewards?: boolean }>> = {
  OperatorProgression: [
    { label: '干员经验', value: 'OperatorEXP', rewards: true },
    { label: '干员进阶', value: 'Promotions', rewards: true },
    { label: '钱币收集', value: 'T-Creds', rewards: false },
    { label: '技能提升', value: 'SkillUp', rewards: true },
  ],
  WeaponProgression: [
    { label: '武器经验', value: 'WeaponEXP', rewards: false },
    { label: '武器进阶', value: 'WeaponTune', rewards: true },
  ],
  CrisisDrills: [
    { label: '高阶培养 I', value: 'AdvancedProgression1', rewards: false },
    { label: '高阶培养 II', value: 'AdvancedProgression2', rewards: false },
    { label: '高阶培养 III', value: 'AdvancedProgression3', rewards: false },
    { label: '高阶培养 IV', value: 'AdvancedProgression4', rewards: false },
    { label: '高阶培养 V', value: 'AdvancedProgression5', rewards: false },
  ],
}

const rewardOptions = [
  { label: '奖励组 A', value: 'RewardsSetA' },
  { label: '奖励组 B', value: 'RewardsSetB' },
]

const protocolTaskFieldMap: Record<string, string> = {
  OperatorProgression: 'OperatorProgression',
  WeaponProgression: 'WeaponProgression',
  CrisisDrills: 'CrisisDrills',
}

const taskLabelMap: Record<string, string> = {
  OperatorProgression: '干员养成任务',
  WeaponProgression: '武器养成任务',
  CrisisDrills: '危境预演任务',
}

const taskTooltipMap: Record<string, string> = {
  OperatorProgression: '选择要执行的干员养成任务',
  WeaponProgression: '选择要执行的武器养成任务',
  CrisisDrills: '选择要执行的危境预演任务',
}

const currentField = computed(() => protocolTaskFieldMap[props.formData.Task.ProtocolSpaceTab])

const currentTaskOptions = computed(
  () => taskOptionsMap[props.formData.Task.ProtocolSpaceTab] ?? taskOptionsMap.OperatorProgression
)

const currentTaskValue = computed({
  get: () => props.formData.Task[currentField.value],
  set: value => {
    props.formData.Task[currentField.value] = value
  },
})

const currentTaskOption = computed(() => {
  return currentTaskOptions.value.find(option => option.value === currentTaskValue.value)
})

const taskOptionLabel = computed(
  () => taskLabelMap[props.formData.Task.ProtocolSpaceTab] ?? '干员养成任务'
)

const taskOptionTooltip = computed(
  () => taskTooltipMap[props.formData.Task.ProtocolSpaceTab] ?? '选择要执行的干员养成任务'
)

const rewardGroupEnabled = computed(() => Boolean(currentTaskOption.value?.rewards))

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const ensureCurrentTaskValue = () => {
  const options = currentTaskOptions.value
  if (!options.some(option => option.value === currentTaskValue.value)) {
    currentTaskValue.value = options[0].value
  }
}

const ensureRewardGroupState = () => {
  if (!rewardGroupEnabled.value && props.formData.Task.RewardsSetOption !== 'RewardsSetA') {
    props.formData.Task.RewardsSetOption = 'RewardsSetA'
    emitSave('Task.RewardsSetOption', props.formData.Task.RewardsSetOption)
  }
}

const handleProtocolSpaceChange = () => {
  ensureCurrentTaskValue()
  emitSave('Task.ProtocolSpaceTab', props.formData.Task.ProtocolSpaceTab)
  emitSave(`Task.${currentField.value}`, currentTaskValue.value)
  ensureRewardGroupState()
}

const handleTaskOptionChange = () => {
  emitSave(`Task.${currentField.value}`, currentTaskValue.value)
  ensureRewardGroupState()
}

watch(
  () => props.formData.Task.ProtocolSpaceTab,
  () => {
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
</style>
