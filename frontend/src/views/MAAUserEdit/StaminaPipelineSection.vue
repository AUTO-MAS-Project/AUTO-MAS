<template>
  <div class="stamina-pipeline">
    <p class="pipeline-overview">{{ t('core.maaStaminaPipeline.orderHint') }}</p>
    <PipelineRow
      :name="t('core.eventDepotPreview.name')"
      :step="1"
      :summary="eventDepotSummary"
      :checked="formData.Task.IfEventDepotMaintain"
      :disabled="loading"
      :hint="eventDepotHint"
      @change="emitSave('Task.IfEventDepotMaintain', $event)"
    >
      <EventDepotPlanEditor
        :editor="eventDepotPlanEditor"
        :loading="loading"
        :stages="activityStages"
        :template="activityTemplate"
        :item-options="depotItemOptions"
        :item-options-error="depotItemOptionsError"
        :inventory="depotInventory"
        :depot-inventory-time="depotInventoryTime"
        :activity-loading="activityStageLoading"
        :activity-error="activityStageError"
        @retry-activity="emit('retryActivity')"
      />
      <a-form-item v-for="field in eventDepotQuotas" :key="field.key" class="quota-count-field">
        <template #label>
          <FieldLabelWithHint
            :text="t(field.labelKey)"
            :hint="t('core.maaStaminaPipeline.quotaCountHint')"
          />
        </template>
        <a-input-number
          :value="formData.Task[field.key]"
          :min="0"
          :max="9999"
          :precision="0"
          allow-clear
          :placeholder="t('core.maaStaminaPipeline.quotaCountPlaceholder')"
          :disabled="loading"
          @change="emitSave('Task.' + field.key, $event)"
        />
      </a-form-item>
    </PipelineRow>
    <!-- 库存保持与养成界面按独立任务并列展示；两者共同启用时后端合成一份
         联合计划执行（先备养成材料，再补足库存，最后培养），口径见行尾 ? -->
    <PipelineRow
      :name="t('core.edit.maaCultivate')"
      :step="2"
      :summary="cultivateSummary"
      :checked="formData.Task.IfCultivate"
      :disabled="loading"
      :has-detail="false"
      :hint="t('core.maaStaminaPipeline.executionHint')"
      @change="emitSave('Task.IfCultivate', $event)"
    >
      <template #actions>
        <a-button :disabled="loading || !route.params.userId" @click="openCultivation">
          {{ t('core.maaCopilot.openPage') }}
        </a-button>
      </template>
    </PipelineRow>
    <PipelineRow
      :name="t('core.edit.maaDepot')"
      :step="3"
      :summary="depotSummary"
      :checked="formData.Task.IfDepotMaintain"
      :disabled="loading"
      :has-detail="false"
      :hint="t('core.maaStaminaPipeline.inventoryHint')"
      @change="emitSave('Task.IfDepotMaintain', $event)"
    >
      <template #actions>
        <a-button :disabled="loading" aria-haspopup="dialog" @click="depotSettingsOpen = true">
          {{ t('core.edit.maaDepotSettings') }}
        </a-button>
      </template>
    </PipelineRow>
    <a-modal
      v-model:open="depotSettingsOpen"
      :title="t('core.edit.maaDepotSettings')"
      :width="1100"
      wrap-class-name="maa-plan-settings-modal"
      centered
      destroy-on-close
      :closable="!loading"
      :mask-closable="!loading"
      :keyboard="!loading"
    >
      <DepotMaintainPlanEditor
        :editor="depotPlanEditor"
        :form-data="formData"
        :loading="loading"
        :stage-options="stageOptions"
        :item-options="depotItemOptions"
        :item-options-loading="depotItemOptionsLoading"
        :item-options-error="depotItemOptionsError"
        :stage-candidates="depotStageCandidates"
        :stage-candidates-loading="depotStageCandidatesLoading"
        :inventory="depotInventory"
        :depot-inventory-time="depotInventoryTime"
      />
      <a-form-item v-for="field in depotQuotas" :key="field.key" class="quota-count-field">
        <template #label>
          <FieldLabelWithHint
            :text="t(field.labelKey)"
            :hint="t('core.maaStaminaPipeline.quotaCountHint')"
          />
        </template>
        <a-input-number
          :value="formData.Task[field.key]"
          :min="0"
          :max="9999"
          :precision="0"
          allow-clear
          :placeholder="t('core.maaStaminaPipeline.quotaCountPlaceholder')"
          :disabled="loading"
          @change="emitSave('Task.' + field.key, $event)"
        />
      </a-form-item>
      <template #footer>
        <a-button :disabled="loading" @click="depotSettingsOpen = false">
          {{ t('core.common.close') }}
        </a-button>
      </template>
    </a-modal>

    <!-- 理智作战 -->
    <PipelineRow
      :name="t('core.maaStaminaPipeline.sanityFallback')"
      :step="4"
      :hint="t('core.maaStaminaPipeline.sanityHint')"
      :summary="fightSummary"
      :checked="formData.Task.IfFight"
      :disabled="loading"
      @change="emitSave('Task.IfFight', $event)"
    >
      <slot name="fight-detail" />
    </PipelineRow>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import PipelineRow from './PipelineRow.vue'
import DepotMaintainPlanEditor from './DepotMaintainPlanEditor.vue'
import EventDepotPlanEditor from './EventDepotPlanEditor.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useRoute, useRouter } from 'vue-router'
import {
  eventDepotPlanIdentity,
  eventStageIdentity,
  getEventDepotStages,
  getEventOrundumStages,
} from './eventDepotMaintainPresets'
import { summarizeCultivate, summarizeDepot } from './taskSummaries'
import type { DepotMaintainPlanEditorState } from './useDepotMaintainPlanEditor'
import type { ActivityItem } from '@/types/home'

type SelectOption = { label: string; value: string }
type QuotaField = { key: string; labelKey: string }

/* 理智药与源石在 MAA 侧同构，两组各两行；新增额度字段只需在这里加一行 */
const eventDepotQuotas: QuotaField[] = [
  {
    key: 'EventDepotMaintainMedicineNumb',
    labelKey: 'core.maaStaminaPipeline.eventDepotMedicineCount',
  },
  { key: 'EventDepotMaintainStoneNumb', labelKey: 'core.maaStaminaPipeline.eventDepotStoneCount' },
]
const depotQuotas: QuotaField[] = [
  { key: 'DepotMaintainMedicineNumb', labelKey: 'core.maaStaminaPipeline.depotMedicineCount' },
  { key: 'DepotMaintainStoneNumb', labelKey: 'core.maaStaminaPipeline.depotStoneCount' },
]

const formData = defineModel<any>('formData', { required: true })
const props = defineProps<{
  loading: boolean
  stageOptions: SelectOption[]
  activityStages: ActivityItem[]
  activityTemplate?: ('material' | 'orundum')[]
  activityStageLoading: boolean
  activityStageError: string
  depotItemOptions: SelectOption[]
  depotPlanEditor: DepotMaintainPlanEditorState
  eventDepotPlanEditor: DepotMaintainPlanEditorState
  depotItemOptionsLoading: boolean
  depotItemOptionsError: string
  depotStageCandidates: Record<string, SelectOption[]>
  depotStageCandidatesLoading: string[]
  depotInventory: Record<string, number>
  depotInventoryTime: string
  fightSummary: string
}>()
const emit = defineEmits<{
  save: [key: string, value: any]
  retryActivity: []
}>()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const openCultivation = () =>
  router.push({
    name: 'MAACultivate',
    params: { scriptId: route.params.scriptId, userId: route.params.userId },
  })
const depotSettingsOpen = ref(false)
const emitSave = (key: string, value: any) => emit('save', key, value)
/* 长说明只留一行摘要，细读内容收进行尾 ? 的 tooltip（见 PipelineRow） */
const eventDepotHint = computed(() =>
  [t('core.eventDepotPreview.hint'), t('core.eventDepotPreview.scopeHint')].join(' ')
)
const cultivateSummary = computed(() =>
  summarizeCultivate(
    {
      enabled: formData.value.Task.IfCultivate,
      targetsJson: formData.value.Task.CultivateTargets,
      autoRaise: formData.value.Task.CultivateAutoRaise ?? false,
    },
    t
  )
)
const depotSummary = computed(() =>
  summarizeDepot(formData.value.Task.IfDepotMaintain, formData.value.Task.DepotMaintainPlans, t)
)
const eventDepotSummary = computed(() => {
  if (!formData.value.Task.IfEventDepotMaintain) return ''
  if (props.activityStageLoading) return t('core.eventDepotPreview.loading')
  if (props.activityStageError) return t('core.eventDepotPreview.dataUnavailable')
  const material = getEventDepotStages(props.activityStages)
  const orundum = getEventOrundumStages(props.activityStages)
  if (!material.length && !orundum.length) return t('core.eventDepotPreview.noActivity')
  // 勾选状态才是实际刷取范围：未勾选的关卡不计入摘要。
  const skipped = new Set(
    props.eventDepotPlanEditor.plans.value.filter(plan => plan.Skip).map(eventDepotPlanIdentity)
  )
  const farmed = [
    ...material.filter((_, index) => !skipped.has(eventStageIdentity('material', index + 1))),
    ...orundum.filter((_, index) => !skipped.has(eventStageIdentity('orundum', index + 1))),
  ]
  const count = new Set(farmed.map(stage => `${stage.Value}:${stage.Drop}`)).size
  return t('core.eventDepotPreview.summary', { n: count })
})
</script>

<style scoped>
.pipeline-overview {
  margin: 6px 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
:deep(.ant-select),
:deep(.ant-input-number) {
  width: 100%;
}
.quota-count-field {
  max-width: 380px;
}
</style>
