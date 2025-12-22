<template>
  <div class="form-section">
    <div class="section-header">
      <h3>关卡配置</h3>
      <!-- 只在计划表模式时显示跳转按钮 -->
      <a-button v-if="isPlanMode" type="link" class="plans-button" @click="handleGoToPlans">
        <template #icon>
          <CalendarOutlined />
        </template>
        跳转到计划表
      </a-button>
    </div>
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="剿灭代理关卡选择">
              <span class="form-label">
                剿灭代理
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.Annihilation"
            :options="[
              { label: '关闭', value: 'Close' },
              { label: '当期剿灭', value: 'Annihilation' },
              { label: '切尔诺伯格', value: 'Chernobog@Annihilation' },
              { label: '龙门外环', value: 'LungmenOutskirts@Annihilation' },
              { label: '龙门市区', value: 'LungmenDowntown@Annihilation' },
            ]"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.Annihilation', formData.Info.Annihilation)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="可选择「固定」或「计划表」">
              <span class="form-label">
                关卡配置模式
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.StageMode"
            :options="stageModeOptions"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.StageMode', formData.Info.StageMode)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="24">
      <a-col :span="6">
        <a-form-item name="medicineNumb">
          <template #label>
            <a-tooltip title="吃理智药数量">
              <span class="form-label">
                吃理智药数量
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displayMedicineNumb }}</div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(medicineNumbTooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
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
            size="large"
            style="width: 100%"
            @update:value="$emit('update-medicine-numb', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip
              title="AUTO：自动识别关卡最大代理倍率，保持最大代理倍率且使用理智药后理智不溢出；数值（1~6）：按设定倍率执行代理；不切换：不调整游戏内代理倍率设定"
            >
              <span class="form-label">
                连战次数
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
              { label: '不切换', value: '-1' },
            ]"
            :disabled="loading"
            size="large"
            @update:value="$emit('update-series-numb', $event)"
          />
        </a-form-item>
      </a-col>

      <a-col :span="12">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="关卡选择">
              <span class="form-label">
                关卡选择
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
          <StageSelector
            v-else
            :value="displayStage"
            :options="stageOptions"
            :loading="loading"
            placeholder="选择或输入自定义关卡"
            @update:value="$emit('update-stage', $event)"
            @add-custom-stage="handleAddCustomStage"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="24">
      <a-col :span="6">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="备选关卡-1，所有备选关卡均选择「当前/上次」时视为不使用备选关卡">
              <span class="form-label">
                备选关卡-1
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
          <StageSelector
            v-else
            :value="displayStage1"
            :options="stageOptions"
            :loading="loading"
            placeholder="选择或输入自定义关卡"
            @update:value="$emit('update-stage1', $event)"
            @add-custom-stage="handleAddCustomStage1"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="备选关卡-2，所有备选关卡均选择「当前/上次」时视为不使用备选关卡">
              <span class="form-label">
                备选关卡-2
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
          <StageSelector
            v-else
            :value="displayStage2"
            :options="stageOptions"
            :loading="loading"
            placeholder="选择或输入自定义关卡"
            @update:value="$emit('update-stage2', $event)"
            @add-custom-stage="handleAddCustomStage2"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="备选关卡-3，所有备选关卡均选择「当前/上次」时视为不使用备选关卡">
              <span class="form-label">
                备选关卡-3
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
          <StageSelector
            v-else
            :value="displayStage3"
            :options="stageOptions"
            :loading="loading"
            placeholder="选择或输入自定义关卡"
            @update:value="$emit('update-stage3', $event)"
            @add-custom-stage="handleAddCustomStage3"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="mode">
          <template #label>
            <a-tooltip title="剩余理智关卡，选择「不选择」时视为不使用剩余理智关卡">
              <span class="form-label">
                剩余理智关卡
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <!-- 计划模式：显示只读文本 -->
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">
              {{ displayStageRemain === '-' ? '不选择' : displayStageRemain || '不选择' }}
            </div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip" v-html="formatTooltip(stageRemainTooltip)"></div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <!-- 固定模式：显示选择框 -->
          <StageSelector
            v-else
            :value="displayStageRemain"
            :options="stageRemainOptions"
            :loading="loading"
            placeholder="选择或输入自定义关卡"
            @update:value="$emit('update-stage-remain', $event)"
            @add-custom-stage="handleAddCustomStageRemain"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { CalendarOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import StageSelector from './StageSelector.vue'
import { navigateTo } from '@/router'

const props = defineProps<{
  formData: any
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
    props.isPlanMode && props.formData?.Info?.StageMode && props.formData.Info.StageMode !== 'Fixed'
      ? props.formData.Info.StageMode
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
</style>
