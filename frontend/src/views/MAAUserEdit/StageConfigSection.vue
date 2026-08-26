<template>
  <div>
    <a-row :gutter="16">
      <a-col :xs="24" :md="12">
        <a-form-item name="mode">
          <template #label>
            <LabelWithHint
              text="关卡配置模式"
              hint="「固定」直接在此配置关卡；「计划表」按计划自动切换"
            />
          </template>
          <a-select v-model:value="formData.Info.StageMode" :options="stageModeOptions" :disabled="loading"
            @change="emitSave('Info.StageMode', formData.Info.StageMode)" />
        </a-form-item>
      </a-col>
      <a-col v-if="isPlanMode" :xs="24" :md="12" class="plans-link-col">
        <a-button type="link" class="plans-button" @click="handleGoToPlans">
          <template #icon>
            <CalendarOutlined />
          </template>
          跳转到计划表
        </a-button>
      </a-col>
    </a-row>
    <a-row :gutter="16">
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="medicineNumb">
          <template #label>
            <LabelWithHint text="吃理智药数量" />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displayMedicineNumb }}</div>
            <a-tooltip>
              <template #title>
                <!-- eslint-disable vue/no-v-html -- formatTooltip escapes all HTML before converting newlines to br tags. -->
                <div class="plan-tooltip" v-html="formatTooltip(medicineNumbTooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示输入框 -->
          <a-input-number v-else :value="displayMedicineNumb" :min="0" :max="9999" placeholder="0" :disabled="loading"
            style="width: 100%" @update:value="$emit('update-medicine-numb', $event)" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <LabelWithHint
              text="连战次数"
              hint="AUTO：自动识别关卡最大代理倍率，保持最大代理倍率且使用理智药后理智不溢出；数值（1~6）：按设定倍率执行代理；不切换：不调整游戏内代理倍率设定"
            />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{
                displaySeriesNumb === '0'
                  ? 'AUTO'
                  : displaySeriesNumb === '-1'
                    ? '不切换'
                    : displaySeriesNumb
              }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(seriesNumbTooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <a-select v-else :value="displaySeriesNumb" :options="[
            { label: 'AUTO', value: '0' },
            { label: '1', value: '1' },
            { label: '2', value: '2' },
            { label: '3', value: '3' },
            { label: '4', value: '4' },
            { label: '5', value: '5' },
            { label: '6', value: '6' },
            { label: '不切换', value: '-1' },
          ]" :disabled="loading" @update:value="$emit('update-series-numb', $event)" />
        </a-form-item>
      </a-col>

      <a-col :xs="24" :xl="12">
        <a-form-item name="mode">
          <template #label>
            <LabelWithHint text="关卡选择" />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{ displayStage === '-' ? '当前/上次' : displayStage || '不选择' }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stageTooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector v-else :value="displayStage" :options="stageOptions" :loading="loading"
            placeholder="选择或输入自定义关卡" @update:value="$emit('update-stage', $event)"
            @add-custom-stage="handleAddCustomStage" />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="16">
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <LabelWithHint
              text="备选关卡-1"
              hint="所有备选关卡均选择「当前/上次」时视为不使用备选关卡"
            />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{ displayStage1 === '-' ? '当前/上次' : displayStage1 || '不选择' }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stage1Tooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector v-else :value="displayStage1" :options="stageOptions" :loading="loading"
            placeholder="选择或输入自定义关卡" @update:value="$emit('update-stage1', $event)"
            @add-custom-stage="handleAddCustomStage1" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <LabelWithHint
              text="备选关卡-2"
              hint="所有备选关卡均选择「当前/上次」时视为不使用备选关卡"
            />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{ displayStage2 === '-' ? '当前/上次' : displayStage2 || '不选择' }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stage2Tooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector v-else :value="displayStage2" :options="stageOptions" :loading="loading"
            placeholder="选择或输入自定义关卡" @update:value="$emit('update-stage2', $event)"
            @add-custom-stage="handleAddCustomStage2" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <LabelWithHint
              text="备选关卡-3"
              hint="所有备选关卡均选择「当前/上次」时视为不使用备选关卡"
            />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{ displayStage3 === '-' ? '当前/上次' : displayStage3 || '不选择' }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stage3Tooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector v-else :value="displayStage3" :options="stageOptions" :loading="loading"
            placeholder="选择或输入自定义关卡" @update:value="$emit('update-stage3', $event)"
            @add-custom-stage="handleAddCustomStage3" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <LabelWithHint text="剩余理智关卡" hint="选择「不选择」时视为不使用剩余理智关卡" />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{ displayStageRemain === '-' ? '不选择' : displayStageRemain || '不选择' }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stageRemainTooltip)"></div>
                <!-- eslint-enable vue/no-v-html -->
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector v-else :value="displayStageRemain" :options="stageRemainOptions" :loading="loading"
            placeholder="选择或输入自定义关卡" @update:value="$emit('update-stage-remain', $event)"
            @add-custom-stage="handleAddCustomStageRemain" />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { CalendarOutlined } from '@ant-design/icons-vue'
import LabelWithHint from './LabelWithHint.vue'
import StageSelector from './StageSelector.vue'
import { navigateTo } from '@/router'

const formData = defineModel<any>('formData', { required: true })
const props = defineProps<{
  loading: boolean
  stageModeOptions: any[]
  stageOptions: any[]
  stageRemainOptions: any[]
  isPlanMode: boolean
  displayMedicineNumb: number
  displaySeriesNumb: string
  displayStage: string
  displayStage1: string
  displayStage2: string
  displayStage3: string
  displayStageRemain: string
  medicineNumbTooltip: string
  seriesNumbTooltip: string
  stageTooltip: string
  stage1Tooltip: string
  stage2Tooltip: string
  stage3Tooltip: string
  stageRemainTooltip: string
}>()

const emit = defineEmits<{
  'update-medicine-numb': [value: number]
  'update-series-numb': [value: string]
  'update-stage': [value: string]
  'update-stage1': [value: string]
  'update-stage2': [value: string]
  'update-stage3': [value: string]
  'update-stage-remain': [value: string]
  'handle-add-custom-stage': [stageName: string]
  'handle-add-custom-stage1': [stageName: string]
  'handle-add-custom-stage2': [stageName: string]
  'handle-add-custom-stage3': [stageName: string]
  'handle-add-custom-stage-remain': [stageName: string]
  'save': [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

// 事件处理函数
const handleAddCustomStage = (stageName: string) => emit('handle-add-custom-stage', stageName)
const handleAddCustomStage1 = (stageName: string) => emit('handle-add-custom-stage1', stageName)
const handleAddCustomStage2 = (stageName: string) => emit('handle-add-custom-stage2', stageName)
const handleAddCustomStage3 = (stageName: string) => emit('handle-add-custom-stage3', stageName)
const handleAddCustomStageRemain = (stageName: string) =>
  emit('handle-add-custom-stage-remain', stageName)

// 跳转到计划表
const handleGoToPlans = () => {
  const planId =
    props.isPlanMode && formData.value?.Info?.StageMode && formData.value.Info.StageMode !== 'Fixed'
      ? formData.value.Info.StageMode
      : undefined
  navigateTo('/plans', { query: { from: 'stage-config', ...(planId ? { planId } : {}) } })
}

// 格式化 tooltip
const escapeHtml = (text: string) =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const formatTooltip = (text: string) => (text ? escapeHtml(text).replace(/\n/g, '<br/>') : '')
</script>

<style scoped>
.plans-link-col {
  display: flex;
  align-items: flex-end;
  padding-bottom: 24px;
}

.plans-button {
  font-size: 14px;
  color: var(--ant-color-primary);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
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
}

.plan-value {
  font-size: 14px;
  color: var(--ant-color-text);
  font-weight: 500;
  flex: 1;
}

.plan-source {
  font-size: 12px;
  color: var(--ant-color-primary);
  font-weight: 500;
  padding: 2px 8px;
  background: var(--ant-color-primary-bg);
  border-radius: 12px;
  border: 1px solid var(--ant-color-primary);
}

.plan-tooltip {
  white-space: normal;
  line-height: 1.5;
  max-width: 320px;
  font-size: 12px;
}

:deep(.ant-form-item) {
  margin-bottom: 12px;
}
</style>
