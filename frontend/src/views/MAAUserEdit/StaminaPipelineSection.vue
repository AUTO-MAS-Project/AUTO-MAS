<template>
  <div class="stamina-pipeline">
    <p class="pipeline-overview">{{ t('maaStaminaPipeline.orderHint') }}</p>
    <PipelineRow
      :name="t('eventDepotPreview.name')"
      :summary="eventDepotSummary"
      :checked="formData.Task.IfEventDepotMaintain"
      :disabled="loading"
      :hint="t('eventDepotPreview.hint')"
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
      <div class="activity-settings">
        <a-form-item :label="t('edit.maaEventPotion')" class="medicine-setting">
          <a-input-number
            :value="formData.Task.ActivityMedicineNumb"
            :min="0"
            :max="9999"
            :disabled="loading"
            @change="emitSave('Task.ActivityMedicineNumb', $event ?? 0)"
          />
        </a-form-item>
        <span class="section-note">{{ t('eventDepotPreview.medicineHint') }}</span>
      </div>
      <div v-if="legacyPlansAvailable" class="recovery-settings">
        <span class="section-note">{{ t('maaStaminaPipeline.recoverHint') }}</span>
        <a-button
          size="small"
          :disabled="loading"
          :loading="recoveringActivity"
          @click="recoverActivityPlans"
        >
          {{ t('maaStaminaPipeline.recoverActivity') }}
        </a-button>
      </div>
    </PipelineRow>
    <PipelineRow
      :name="t('maaStaminaPipeline.inventoryCultivate')"
      :summary="inventoryCultivateSummary"
      :checked="formData.Task.IfDepotMaintain || formData.Task.IfCultivate"
      :toggleable="false"
      :hint="t('maaStaminaPipeline.inventoryHint')"
    >
      <a-alert
        :message="t('maaStaminaPipeline.executionHint')"
        type="info"
        show-icon
        class="pipeline-alert"
      />
      <!-- 两个来源分别保留原开关与设置，按本轮适用条件共同规划。 -->
      <CultivateTargetEditor
        :summary="cultivateSummary"
        :form-data="formData"
        :loading="loading"
        :operator-catalog="cultivateOperatorCatalog"
        :operator-options-loading="cultivateOperatorOptionsLoading"
        :operator-options-error="cultivateOperatorOptionsError"
        :skland-role-options="sklandRoleOptions"
        :skland-role-loading="sklandRoleLoading"
        :skland-role-error="sklandRoleError"
        :load-skland-role-options="loadSklandRoleOptions"
        :item-options="depotItemOptions"
        :cultivate-preview="cultivatePreview"
        :cultivate-preview-loading="cultivatePreviewLoading"
        :cultivate-preview-error="cultivatePreviewError"
        :load-cultivate-preview="loadCultivatePreview"
        :import-cultivate-targets="importCultivateTargets"
        @save="emitSave"
      />
      <!-- 固定与计划表仅控制第三段，库存目标仍独立保存。 -->
      <PipelineRow
        :name="t('edit.maaDepot')"
        :summary="depotSummary"
        :checked="formData.Task.IfDepotMaintain"
        :disabled="loading"
        :has-detail="false"
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
    </PipelineRow>

    <!-- 理智作战 -->
    <PipelineRow
      :name="t('maaStaminaPipeline.sanityFallback')"
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
import { message } from 'ant-design-vue'
import PipelineRow from './PipelineRow.vue'
import DepotMaintainPlanEditor from './DepotMaintainPlanEditor.vue'
import CultivateTargetEditor from './CultivateTargetEditor.vue'
import {
  getLegacyEventDepotPlans,
  eventDepotPlanIdentity,
  getEventDepotStages,
  getEventOrundumStages,
  resolveEventDepotStage,
} from './eventDepotMaintainPresets'
import { summarizeCultivate, summarizeDepot } from './taskSummaries'
import type { DepotMaintainPlanEditorState } from './useDepotMaintainPlanEditor'
import type { CultivateImportResult, CultivateOperatorCatalogEntry } from './cultivateTargets'
import type { CultivatePreviewOut } from '@/api'
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
  cultivateOperatorCatalog: CultivateOperatorCatalogEntry[]
  sklandRoleOptions: SelectOption[]
  sklandRoleLoading: boolean
  sklandRoleError: string
  loadSklandRoleOptions: () => Promise<void>
  cultivateOperatorOptionsLoading: boolean
  cultivateOperatorOptionsError: string
  cultivatePreview: CultivatePreviewOut | null
  cultivatePreviewLoading: boolean
  cultivatePreviewError: string
  loadCultivatePreview: (targetsJson: string) => Promise<void>
  importCultivateTargets: (content: string) => Promise<CultivateImportResult>
  fightSummary: string
  recoverActivityPlans: () => Promise<void>
}>()
const emit = defineEmits<{
  save: [key: string, value: any]
  retryActivity: []
}>()
const { t } = useI18n()
const depotSettingsOpen = ref(false)
const recoveringActivity = ref(false)
const emitSave = (key: string, value: any) => emit('save', key, value)
const legacyPlansAvailable = computed(() => {
  const saved = new Set(props.eventDepotPlanEditor.plans.value.map(eventDepotPlanIdentity))
  return getLegacyEventDepotPlans(formData.value.Data?.StaminaPipelineBackup ?? '{}').some(
    plan => !saved.has(eventDepotPlanIdentity(plan))
  )
})
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
const inventoryCultivateSummary = computed(() =>
  [
    depotSummary.value || t('maaStaminaPipeline.inventoryOff'),
    cultivateSummary.value || t('maaStaminaPipeline.cultivateOff'),
  ].join(' · ')
)
const eventDepotSummary = computed(() => {
  if (!formData.value.Task.IfEventDepotMaintain) return ''
  if (props.activityStageLoading) return t('eventDepotPreview.loading')
  if (props.activityStageError) return t('eventDepotPreview.dataUnavailable')
  const available = [
    ...getEventDepotStages(props.activityStages),
    ...getEventOrundumStages(props.activityStages),
  ]
  if (!available.length) return t('eventDepotPreview.noActivity')
  const resolved = props.eventDepotPlanEditor.plans.value.flatMap(plan =>
    plan.StageType === 'all'
      ? available
      : [resolveEventDepotStage(props.activityStages, plan)].filter(
          (stage): stage is ActivityItem => !!stage
        )
  )
  const count = new Set(resolved.map(stage => `${stage.Value}:${stage.Drop}`)).size
  return count ? t('eventDepotPreview.summary', { n: count }) : t('edit.maaDepotEmpty')
})
const recoverActivityPlans = async () => {
  recoveringActivity.value = true
  try {
    await props.recoverActivityPlans()
  } catch (error) {
    message.error(error instanceof Error ? error.message : String(error))
  } finally {
    recoveringActivity.value = false
  }
}
</script>

<style scoped>
.pipeline-overview,
.section-note {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
.pipeline-overview {
  margin: 6px 4px;
}
.pipeline-alert {
  margin-bottom: 12px;
}
.activity-settings,
.recovery-settings {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 12px;
}
.medicine-setting {
  margin-bottom: 0;
  width: 160px;
}
.recovery-settings {
  justify-content: space-between;
}
:deep(.ant-select),
:deep(.ant-input-number) {
  width: 100%;
}
</style>
