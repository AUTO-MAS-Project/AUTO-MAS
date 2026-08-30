<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.taskConfiguration') }}</h3>
      <span class="section-note">{{ t('edit.annihilationDailyRunStart') }}</span>
    </div>

    <a-alert
      :message="t('edit.annihilationDailyTasksEach')"
      :description="t('edit.annihilationMaaStartsOnce')"
      type="info"
      show-icon
      class="task-alert"
    />

    <a-alert
      v-if="activityStageError"
      :message="activityStageError"
      type="warning"
      show-icon
      class="task-alert"
    />

    <div class="task-list">
      <div class="pipeline-phase">{{ t('edit.firstMaaSessionAnnihilation') }}</div>
      <PipelineRow
        name="剿灭作战"
        :summary="annihilationSummary"
        :checked="annihilationEnabled"
        :disabled="loading"
        hint="这是一次独立的 MAA 启动，仅执行唤醒和剿灭作战；不会在同一次启动中继续日常任务"
        @change="handleAnnihilationToggle"
      >
        <a-row :gutter="16">
          <a-col :xs="24" :md="12">
            <a-form-item :label="t('edit.annihilationStage')" class="detail-item">
              <a-select
                :value="formData.Info.Annihilation"
                :options="annihilationStageOptions"
                :disabled="loading"
                @change="emitSave('Info.Annihilation', $event)"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item class="detail-item">
              <template #label>
                <LabelWithHint
                  text="剿灭开始星期"
                  hint="达到设置的星期后才会启动剿灭任务；本周达到上限后会自动跳过后续剿灭"
                />
              </template>
              <a-select
                :value="formData.Info.AnnihilationStartWeekday || 'Monday'"
                :options="annihilationWeekdayOptions"
                :disabled="loading"
                @change="emitSave('Info.AnnihilationStartWeekday', $event)"
              />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <div class="detail-inline">
              <a-tag :color="annihilationCompletedThisWeek ? 'success' : 'warning'">
                本周状态：{{ annihilationCompletedThisWeek ? '已完成' : '未完成' }}
              </a-tag>
              <a-button
                size="small"
                :disabled="loading"
                @click="emitSave('Data.AnnihilationCompletedWeek', null)"
              >
                {{ t('edit.resetState') }}
              </a-button>
              <a-button
                size="small"
                :disabled="loading"
                @click="emitSave('Data.AnnihilationCompletedWeek', currentWeekMarker)"
              >
                {{ t('edit.markAsDone2') }}
              </a-button>
            </div>
          </a-col>
        </a-row>
      </PipelineRow>

      <div class="pipeline-phase">{{ t('edit.secondMaaSessionDaily') }}</div>
      <PipelineRow
        name="活动关优先"
        :summary="activitySummary"
        :checked="activityFirst"
        :disabled="loading"
        hint="这是日常流程中的独立合成任务，会在普通理智作战之前执行"
        @change="handleActivityToggle"
      >
        <a-row :gutter="16">
          <a-col :xs="24" :md="16">
            <a-form-item class="detail-item">
              <template #label>
                <LabelWithHint
                  text="活动关卡"
                  hint="按列表序号保存；活动更新后自动选择相同序号的新关卡，序号失效时回退到第一项"
                />
              </template>
              <a-select
                :value="displayActivityStageIndex"
                :options="activityStageOptions"
                :loading="activityStageLoading"
                :disabled="loading || activityStageLoading || activityStageOptions.length === 0"
                :placeholder="activityStageOptions.length ? '请选择活动关卡' : '当前无可刷活动关'"
                show-search
                option-filter-prop="label"
                @change="handleActivityStageChange"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item class="detail-item">
              <template #label>
                <LabelWithHint
                  text="活动关理智药"
                  hint="活动关优先任务使用的理智药数量，不影响普通理智作战"
                />
              </template>
              <a-input-number
                :value="formData.Task.ActivityMedicineNumb"
                :min="0"
                :max="9999"
                :disabled="loading"
                placeholder="0"
                class="full-width"
                @change="emitSave('Task.ActivityMedicineNumb', $event ?? 0)"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </PipelineRow>

      <!-- 库存保持：日常流程中的独立任务，计划模式下后端强制关闭 -->
      <PipelineRow
        name="库存保持"
        :summary="depotSummary"
        :checked="!isPlanMode && formData.Task.IfDepotMaintain"
        :disabled="loading || isPlanMode"
        :has-detail="!isPlanMode"
        @change="emitSave('Task.IfDepotMaintain', $event)"
      >
        <DepotMaintainPlanEditor
          :form-data="formData"
          :loading="loading"
          :stage-options="stageOptions"
          :item-options="depotItemOptions"
          :item-options-loading="depotItemOptionsLoading"
          :item-options-error="depotItemOptionsError"
          @save="emitSave"
        />
      </PipelineRow>

      <!-- 理智作战 -->
      <PipelineRow
        name="理智作战"
        :summary="fightSummary"
        :checked="formData.Task.IfFight"
        :disabled="loading"
        @change="emitSave('Task.IfFight', $event)"
      >
        <slot name="fight-detail" />
      </PipelineRow>

      <!-- 基建换班：模式与自定义排班是它的附属配置，跟着它走 -->
      <PipelineRow
        name="基建换班"
        :summary="infrastSummary"
        :checked="formData.Task.IfInfrast"
        :disabled="loading"
        @change="emitSave('Task.IfInfrast', $event)"
      >
        <a-row :gutter="16">
          <a-col :xs="24" :md="12">
            <a-form-item class="detail-item">
              <template #label>
                <LabelWithHint
                  text="基建模式"
                  hint="自定义基建需要先导入配置文件，再选择其中的排班"
                />
              </template>
              <a-select
                :value="formData.Info.InfrastMode"
                :options="INFRAST_MODE_OPTIONS"
                :disabled="loading"
                @change="emitSave('Info.InfrastMode', $event)"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row v-if="formData.Info.InfrastMode === 'Custom'" :gutter="16">
          <a-col :xs="24" :md="12">
            <a-form-item class="detail-item">
              <template #label>
                <LabelWithHint text="自定义基建配置" hint="从 MAA 导出的自定义基建 JSON 文件" />
              </template>
              <div class="detail-inline">
                <a-input
                  :value="formData.Info.InfrastName"
                  :placeholder="t('edit.noConfigurationImportedYet')"
                  readonly
                  class="infrast-name"
                />
                <a-button
                  type="primary"
                  :disabled="loading || !isEdit"
                  :loading="infrastructureImporting"
                  @click="emit('selectAndImportInfrastructureConfig')"
                >
                  {{ t('edit.pickImport') }}
                </a-button>
              </div>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item class="detail-item">
              <template #label>
                <LabelWithHint text="自定义基建排班" hint="从已导入的配置中选择当前使用的排班" />
              </template>
              <a-select
                :value="formData.Info.InfrastIndex"
                :options="infrastructureOptions"
                :loading="infrastructureOptionsLoading"
                :disabled="loading"
                :placeholder="t('edit.pickCustomBaseLayout')"
                @change="emitSave('Info.InfrastIndex', $event)"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </PipelineRow>

      <!-- 无配置的一键任务：低频改动，压成一行 -->
      <PipelineRow
        name="日常任务"
        :checked="dailyTasks.some(task => formData.Task[task.key])"
        :toggleable="false"
        :has-detail="false"
      >
        <template #summary>
          <span class="daily-checks">
            <a-checkbox
              v-for="task in dailyTasks"
              :key="task.key"
              :checked="formData.Task[task.key]"
              :disabled="loading"
              @change="emitSave(`Task.${task.key}`, $event.target.checked)"
            >
              {{ task.label }}
            </a-checkbox>
          </span>
        </template>
      </PipelineRow>

      <!-- 只有一个开关，不必套一层详情面板 -->
      <PipelineRow
        name="自动肉鸽"
        :summary="formData.Task.IfRoguelike ? '长时间运行可能被误判超时' : ''"
        :checked="formData.Task.IfRoguelike"
        :disabled="loading"
        :has-detail="false"
        @change="emitSave('Task.IfRoguelike', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import PipelineRow from './PipelineRow.vue'
import LabelWithHint from './LabelWithHint.vue'
import DepotMaintainPlanEditor from './DepotMaintainPlanEditor.vue'
import { currentWeekMarker } from './weekMarker'
import {
  ANNIHILATION_STAGE_OPTIONS as annihilationStageOptions,
  ANNIHILATION_WEEKDAY_OPTIONS as annihilationWeekdayOptions,
  INFRAST_MODE_OPTIONS,
  summarizeActivity,
  summarizeAnnihilation,
  summarizeDepot,
  summarizeInfrast,
} from './taskSummaries'

const { t } = useI18n()

type SelectOption = { label: string; value: string }

const formData = defineModel<any>('formData', { required: true })

const props = defineProps<{
  loading: boolean
  isPlanMode: boolean
  stageOptions: any[]
  activityStageOptions: Array<{ label: string; value: number }>
  activityStageLoading: boolean
  activityStageError: string
  displayActivityStageIndex?: number
  depotItemOptions: SelectOption[]
  depotItemOptionsLoading: boolean
  depotItemOptionsError: string
  fightSummary: string
  isEdit: boolean
  infrastructureImporting: boolean
  infrastructureOptions: SelectOption[]
  infrastructureOptionsLoading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
  selectAndImportInfrastructureConfig: []
}>()
const emitSave = (key: string, value: any) => emit('save', key, value)

const dailyTasks = [
  { key: 'IfRecruit', label: '自动公招' },
  { key: 'IfMall', label: '信用收支' },
  { key: 'IfAward', label: '领取奖励' },
] as const

const annihilationEnabled = computed(() => formData.value.Info.Annihilation !== 'Close')

const annihilationCompletedThisWeek = computed(
  () => formData.value.Data?.AnnihilationCompletedWeek === currentWeekMarker
)

// 关闭时记住原关卡，重新打开直接恢复，省掉一次下拉选择
let lastAnnihilationStage = 'Annihilation'
const handleAnnihilationToggle = (checked: boolean) => {
  if (checked) {
    emitSave('Info.Annihilation', lastAnnihilationStage)
  } else {
    lastAnnihilationStage = formData.value.Info.Annihilation || 'Annihilation'
    emitSave('Info.Annihilation', 'Close')
  }
}

const annihilationSummary = computed(() =>
  summarizeAnnihilation(
    formData.value.Info.Annihilation,
    formData.value.Info.AnnihilationStartWeekday || 'Monday',
    annihilationCompletedThisWeek.value
  )
)

const activityFirst = computed(() => formData.value.Task.IfActivityFirst)

const handleActivityToggle = (checked: boolean) => emitSave('Task.IfActivityFirst', checked)

const handleActivityStageChange = (value: number) => emitSave('Task.ActivityStageIndex', value)

const activitySummary = computed(() =>
  summarizeActivity({
    enabled: activityFirst.value,
    loading: props.activityStageLoading,
    optionCount: props.activityStageOptions.length,
    stageLabel: props.activityStageOptions.find(
      option => option.value === props.displayActivityStageIndex
    )?.label,
    medicine: formData.value.Task.ActivityMedicineNumb ?? 0,
  })
)

const infrastSummary = computed(() => {
  const scheduleLabel = props.infrastructureOptions.find(
    option => option.value === formData.value.Info.InfrastIndex
  )?.label
  const customLabel = [formData.value.Info.InfrastName, scheduleLabel].filter(Boolean).join(' · ')
  return summarizeInfrast(
    formData.value.Task.IfInfrast,
    formData.value.Info.InfrastMode,
    customLabel
  )
})

const depotSummary = computed(() =>
  summarizeDepot(
    props.isPlanMode,
    formData.value.Task.IfDepotMaintain,
    formData.value.Task.DepotMaintainPlans
  )
)
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 8px;
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

.section-note {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.task-alert {
  margin: 12px 0;
}

.pipeline-phase {
  padding: 12px 4px 6px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
}

.daily-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}

.detail-item {
  margin-bottom: 12px;
}

.detail-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.full-width {
  width: 100%;
}

.infrast-name {
  flex: 1;
  min-width: 0;
}

:deep(.ant-select),
:deep(.ant-input-number) {
  width: 100%;
}
</style>
