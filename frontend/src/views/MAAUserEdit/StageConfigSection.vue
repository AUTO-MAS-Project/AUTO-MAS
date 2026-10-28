<template>
  <div>
    <a-row :gutter="16">
      <a-col :xs="24" :md="12">
        <a-form-item name="mode">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.stageConfigMode')"
              :hint="t('core.edit.stageConfigModeHint')"
            />
          </template>
          <a-select
            v-model:value="formData.Stage.StageMode"
            :options="stageModeOptions"
            :disabled="loading"
            @change="emitSave('Stage.StageMode', formData.Stage.StageMode)"
          />
        </a-form-item>
      </a-col>
      <a-col v-if="isPlanMode" :xs="24" :md="12" class="plans-link-col">
        <a-button type="link" class="plans-button" @click="handleGoToPlans">
          <template #icon>
            <CalendarOutlined />
          </template>
          {{ t('core.edit.goPlan') }}
        </a-button>
      </a-col>
    </a-row>
    <a-row :gutter="16">
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="medicineNumb">
          <template #label>
            <FieldLabelWithHint :text="t('core.edit.medicineNumb')" />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displayMedicineNumb }}</div>
            <a-tooltip>
              <template #title>
                <!-- eslint-disable vue/no-v-html -- formatTooltip escapes all HTML before converting newlines to br tags. -->
                <div class="plan-tooltip" v-html="formatTooltip(medicineNumbTooltip)"></div>
              </template>
              <div class="plan-source">{{ t('core.edit.fromPlan') }}</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示输入框 -->
          <a-input-number
            v-else
            :value="displayMedicineNumb"
            :min="0"
            :max="9999"
            placeholder="0"
            :disabled="loading"
            style="width: 100%"
            @update:value="$emit('update-medicine-numb', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.seriesNumb')"
              :hint="t('core.edit.seriesNumbHint')"
            />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{
                displaySeriesNumb === '0'
                  ? 'AUTO'
                  : displaySeriesNumb === '-1'
                    ? t('core.edit.doNotSwitch')
                    : displaySeriesNumb
              }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(seriesNumbTooltip)"></div>
              </template>
              <div class="plan-source">{{ t('core.edit.fromPlan') }}</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <a-select
            v-else
            :value="displaySeriesNumb"
            :options="[
              { label: 'AUTO', value: '0' },
              { label: '1', value: '1' },
              { label: '2', value: '2' },
              { label: '3', value: '3' },
              { label: '4', value: '4' },
              { label: '5', value: '5' },
              { label: '6', value: '6' },
              { label: t('core.edit.doNotSwitch'), value: '-1' },
            ]"
            :disabled="loading"
            @update:value="$emit('update-series-numb', $event)"
          />
        </a-form-item>
      </a-col>

      <a-col :xs="24" :xl="12">
        <a-form-item name="mode">
          <template #label>
            <FieldLabelWithHint :text="t('core.edit.stageSelection')" />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{
                displayStage === '-'
                  ? t('core.edit.currentOrLast')
                  : displayStage || t('core.edit.none')
              }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stageTooltip)"></div>
              </template>
              <div class="plan-source">{{ t('core.edit.fromPlan') }}</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector
            v-else
            :value="displayStage"
            :options="stageOptions"
            :loading="loading"
            :placeholder="t('core.edit.pickTypeCustomStage')"
            @update:value="$emit('update-stage', $event)"
            @add-custom-stage="handleAddCustomStage"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="16">
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.alternateStage', { n: 1 })"
              :hint="t('core.edit.alternateStageHint')"
            />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{
                displayStage1 === '-'
                  ? t('core.edit.currentOrLast')
                  : displayStage1 || t('core.edit.none')
              }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stage1Tooltip)"></div>
              </template>
              <div class="plan-source">{{ t('core.edit.fromPlan') }}</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector
            v-else
            :value="displayStage1"
            :options="stageOptions"
            :loading="loading"
            :placeholder="t('core.edit.pickTypeCustomStage')"
            @update:value="$emit('update-stage1', $event)"
            @add-custom-stage="handleAddCustomStage1"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.alternateStage', { n: 2 })"
              :hint="t('core.edit.alternateStageHint')"
            />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{
                displayStage2 === '-'
                  ? t('core.edit.currentOrLast')
                  : displayStage2 || t('core.edit.none')
              }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stage2Tooltip)"></div>
              </template>
              <div class="plan-source">{{ t('core.edit.fromPlan') }}</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector
            v-else
            :value="displayStage2"
            :options="stageOptions"
            :loading="loading"
            :placeholder="t('core.edit.pickTypeCustomStage')"
            @update:value="$emit('update-stage2', $event)"
            @add-custom-stage="handleAddCustomStage2"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12" :xl="6">
        <a-form-item name="mode">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.alternateStage', { n: 3 })"
              :hint="t('core.edit.alternateStageHint')"
            />
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{
                displayStage3 === '-'
                  ? t('core.edit.currentOrLast')
                  : displayStage3 || t('core.edit.none')
              }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stage3Tooltip)"></div>
              </template>
              <div class="plan-source">{{ t('core.edit.fromPlan') }}</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector
            v-else
            :value="displayStage3"
            :options="stageOptions"
            :loading="loading"
            :placeholder="t('core.edit.pickTypeCustomStage')"
            @update:value="$emit('update-stage3', $event)"
            @add-custom-stage="handleAddCustomStage3"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { CalendarOutlined } from '@ant-design/icons-vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import StageSelector from './StageSelector.vue'
import { navigateTo } from '@/router'

const { t } = useI18n()

const formData = defineModel<any>('formData', { required: true })
const props = defineProps<{
  loading: boolean
  stageModeOptions: any[]
  stageOptions: any[]
  isPlanMode: boolean
  displayMedicineNumb: number
  displaySeriesNumb: string
  displayStage: string
  displayStage1: string
  displayStage2: string
  displayStage3: string
  medicineNumbTooltip: string
  seriesNumbTooltip: string
  stageTooltip: string
  stage1Tooltip: string
  stage2Tooltip: string
  stage3Tooltip: string
}>()

const emit = defineEmits<{
  'update-medicine-numb': [value: number]
  'update-series-numb': [value: string]
  'update-stage': [value: string]
  'update-stage1': [value: string]
  'update-stage2': [value: string]
  'update-stage3': [value: string]
  'handle-add-custom-stage': [stageName: string]
  'handle-add-custom-stage1': [stageName: string]
  'handle-add-custom-stage2': [stageName: string]
  'handle-add-custom-stage3': [stageName: string]
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

// 事件处理函数
const handleAddCustomStage = (stageName: string) => emit('handle-add-custom-stage', stageName)
const handleAddCustomStage1 = (stageName: string) => emit('handle-add-custom-stage1', stageName)
const handleAddCustomStage2 = (stageName: string) => emit('handle-add-custom-stage2', stageName)
const handleAddCustomStage3 = (stageName: string) => emit('handle-add-custom-stage3', stageName)

// 跳转到计划表
const handleGoToPlans = () => {
  const planId =
    props.isPlanMode &&
    formData.value?.Stage?.StageMode &&
    formData.value.Stage.StageMode !== 'Fixed'
      ? formData.value.Stage.StageMode
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
