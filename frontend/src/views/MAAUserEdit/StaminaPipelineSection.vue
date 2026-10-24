<template>
  <div class="stamina-pipeline">
    <p class="pipeline-overview">{{ t('maaStaminaPipeline.orderHint') }}</p>
    <PipelineRow
      :name="t('eventDepotPreview.name')"
      :step="1"
      :summary="eventDepotSummary"
      :checked="formData.Task.IfEventDepotMaintain"
      :disabled="loading"
      :hint="eventDepotHint"
      @change="emitSave('Task.IfEventDepotMaintain', $event)"
    >
      <DepotMaintainPlanEditor
        :editor="eventDepotPlanEditor"
        :form-data="formData"
        :loading="loading"
        :stage-options="stageOptions"
        :item-options="depotItemOptions"
        :item-options-loading="depotItemOptionsLoading"
        :item-options-error="depotItemOptionsError"
        :stage-candidates="{}"
        :stage-candidates-loading="[]"
        :inventory="depotInventory"
        :depot-inventory-time="depotInventoryTime"
        :activity-stages="activityStages"
        :activity-loading="activityStageLoading"
        :activity-error="activityStageError"
        @retry-activity="emit('retryActivity')"
      />
    </PipelineRow>
    <!-- 库存保持与养成界面按独立任务并列展示；两者共同启用时后端合成一份
         联合计划执行（先备养成材料，再补足库存，最后培养），口径见行尾 ? -->
    <PipelineRow
      :name="t('edit.maaCultivate')"
      :step="2"
      :summary="cultivateSummary"
      :checked="formData.Task.IfCultivate"
      :disabled="loading"
      :has-detail="false"
      :hint="t('maaStaminaPipeline.executionHint')"
      @change="emitSave('Task.IfCultivate', $event)"
    >
      <template #actions>
        <a-button :disabled="loading || !route.params.userId" @click="openCultivation">
          {{ t('maaCopilot.openPage') }}
        </a-button>
      </template>
    </PipelineRow>
    <PipelineRow
      :name="t('edit.maaDepot')"
      :step="3"
      :summary="depotSummary"
      :checked="formData.Task.IfDepotMaintain"
      :disabled="loading"
      :has-detail="false"
      :hint="t('maaStaminaPipeline.inventoryHint')"
      @change="emitSave('Task.IfDepotMaintain', $event)"
    >
      <template #actions>
        <a-tooltip :title="t('edit.maaDepotSettings')">
          <a-button
            type="text"
            shape="circle"
            :aria-label="t('edit.maaDepotSettings')"
            aria-haspopup="dialog"
            :disabled="loading"
            @click="depotSettingsOpen = true"
          >
            <template #icon><SettingOutlined /></template>
          </a-button>
        </a-tooltip>
      </template>
    </PipelineRow>
    <a-modal
      v-model:open="depotSettingsOpen"
      :title="t('edit.maaDepotSettings')"
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
      <template #footer>
        <a-button :disabled="loading" @click="depotSettingsOpen = false">
          {{ t('common.close') }}
        </a-button>
      </template>
    </a-modal>

    <!-- 理智作战 -->
    <PipelineRow
      :name="t('maaStaminaPipeline.sanityFallback')"
      :step="4"
      :hint="t('maaStaminaPipeline.sanityHint')"
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
import { SettingOutlined } from '@ant-design/icons-vue'
import PipelineRow from './PipelineRow.vue'
import DepotMaintainPlanEditor from './DepotMaintainPlanEditor.vue'
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

const formData = defineModel<any>('formData', { required: true })
const props = defineProps<{
  loading: boolean
  stageOptions: SelectOption[]
  activityStages: ActivityItem[]
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
  [t('eventDepotPreview.hint'), t('eventDepotPreview.scopeHint')].join(' ')
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
  if (props.activityStageLoading) return t('eventDepotPreview.loading')
  if (props.activityStageError) return t('eventDepotPreview.dataUnavailable')
  const material = getEventDepotStages(props.activityStages)
  const orundum = getEventOrundumStages(props.activityStages)
  if (!material.length && !orundum.length) return t('eventDepotPreview.noActivity')
  // 勾选状态才是实际刷取范围：未勾选的关卡不计入摘要。
  const skipped = new Set(
    props.eventDepotPlanEditor.plans.value.filter(plan => plan.Skip).map(eventDepotPlanIdentity)
  )
  const farmed = [
    ...material.filter((_, index) => !skipped.has(eventStageIdentity('material', index + 1))),
    ...orundum.filter((_, index) => !skipped.has(eventStageIdentity('orundum', index + 1))),
  ]
  const count = new Set(farmed.map(stage => `${stage.Value}:${stage.Drop}`)).size
  return t('eventDepotPreview.summary', { n: count })
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
</style>
