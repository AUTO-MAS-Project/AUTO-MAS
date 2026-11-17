<template>
  <div v-if="formData.Info.IfQuickConfig" class="sanity-section">
    <a-card id="section-sanity" class="section-card">
      <template #title>{{ t('core.edit.maaEndProtocolSpaceTitle') }}</template>
      <SanityStrategySection
        :enabled="formData.Task.IfProtocolSpace"
        :show-detail="formData.Task.IfProtocolSpace"
        :strategy="formData.Info.SanityStrategy"
        :disabled="loading"
        :config-loading="configLoading"
        :show-config-mask="showConfigMask"
        @enable="value => emit('save', 'Task.IfProtocolSpace', value)"
        @save="value => emit('save', 'Info.SanityStrategy', value)"
        @configure="emit('configure')"
      />
      <InventoryConfigSection
        v-if="formData.Task.IfProtocolSpace && formData.Info.SanityStrategy === 'Inventory'"
        :form-data="formData"
        :inventory="inventory"
        :loading="loading"
        :options-loading="optionsLoading"
        @save="(key, value) => emit('save', key, value)"
        @reload="emit('reload')"
      />
      <SanityConfigSection
        v-if="formData.Task.IfProtocolSpace && formData.Info.SanityStrategy === 'MAS'"
        :form-data="formData"
        :loading="loading"
        :crisis-drills-options="crisisDrillsOptions"
        :options-loading="optionsLoading"
        :is-plan-mode="isSanityPlanMode"
        :sanity-mode-options="sanityModeOptions"
        :plan-mode-config="planModeConfig"
        @save="(key, value) => emit('save', key, value)"
        @save-batch="changes => emit('saveBatch', changes)"
      />
      <a-button
        v-if="
          formData.Task.IfProtocolSpace &&
          isSanityPlanMode &&
          formData.Info.SanityStrategy === 'MAS'
        "
        type="link"
        @click="handleGoToPlans(formData.Info.SanityMode)"
      >
        <template #icon><CalendarOutlined /></template>{{ t('core.edit.goPlan') }}
      </a-button>
    </a-card>
    <a-card id="section-essence" class="section-card">
      <template #title>{{ t('core.edit.maaEndEssenceTitle') }}</template>
      <template #extra>
        <a-switch
          :checked="formData.Task.IfAutoEssence"
          :disabled="loading"
          :aria-label="t('core.edit.maaEndEnableEssence')"
          @change="(value: boolean) => emit('save', 'Task.IfAutoEssence', value)"
        />
      </template>
      <EssenceConfigSection
        v-if="formData.Task.IfAutoEssence"
        :form-data="formData"
        :loading="loading"
        :options-loading="optionsLoading"
        :options-loaded="optionsLoaded"
        :config-loading="configLoading"
        :show-config-mask="showConfigMask"
        :essence-location-options="essenceLocationOptions"
        :essence-menu-options="essenceMenuOptions"
        :essence-target-weapon-groups="essenceTargetWeaponGroups"
        :sanity-mode-options="sanityModeOptions"
        :is-plan-mode="isEssencePlanMode"
        :plan-mode-config="essencePlanConfig"
        @save="(key, value) => emit('save', key, value)"
        @configure="emit('configure')"
      />
      <a-button
        v-if="formData.Task.IfAutoEssence && isEssencePlanMode"
        type="link"
        @click="handleGoToPlans(formData.Info.AutoEssenceMode)"
      >
        <template #icon><CalendarOutlined /></template>{{ t('core.edit.goPlan') }}
      </a-button>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { CalendarOutlined } from '@ant-design/icons-vue'
import { navigateTo } from '@/router'
import type { ComboBoxItem, MaaEndInventoryOptions } from '@/api'
import { Service, PlanComboxIn } from '@/api'
import { usePlanApi } from '@/composables/usePlanApi'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
import { getWeekdayInTimezone } from '@/utils/dateUtils'
import { clampRotateDays } from '@/utils/planDays'
import {
  MAAEND_PLAN_WEEKDAY_KEYS,
  maaEndPlanKeyToSanityConfig,
  type MaaEndSanityConfig,
  type MaaEndEssenceTargetGroup,
} from '@/utils/maaEndProtocolSpace'
import type { MaaEndUserForm } from './userDefaults'
import InventoryConfigSection from './InventoryConfigSection.vue'
import SanityConfigSection from './SanityConfigSection.vue'
import SanityStrategySection from './SanityStrategySection.vue'
import EssenceConfigSection from './EssenceConfigSection.vue'

const props = defineProps<{
  formData: MaaEndUserForm
  loading: boolean
  inventory: MaaEndInventoryOptions | null
  crisisDrillsOptions: ComboBoxItem[]
  essenceLocationOptions: ComboBoxItem[]
  essenceMenuOptions: ComboBoxItem[]
  essenceTargetWeaponGroups: MaaEndEssenceTargetGroup[]
  optionsLoading: boolean
  optionsLoaded: boolean
  configLoading: boolean
  showConfigMask: boolean
}>()
const emit = defineEmits<{
  save: [key: string, value: unknown]
  saveBatch: [changes: Array<{ key: string; value: unknown }>]
  configure: []
  reload: []
}>()
const { t } = useI18n()
const { getPlans } = usePlanApi()
const logger = window.electronAPI.getLogger('MaaEnd理智配置')
const formData = props.formData
const sanityModeOptions = ref<Array<{ label: string; value: string }>>([
  { label: t('core.edit.fixed'), value: 'Fixed' },
])
const planModeConfig = ref<MaaEndSanityConfig | null>(null)
const essencePlanConfig = ref<MaaEndSanityConfig | null>(null)
// 计划表切换版本号：loadSanityPlan 每次调用自增，用于丢弃过期的异步响应
const planLoadVersion = { protocol: 0, essence: 0 }
const isSanityPlanMode = computed(() => formData.Info.SanityMode !== 'Fixed')
const isEssencePlanMode = computed(
  () => !['Fixed', 'Native'].includes(formData.Info.AutoEssenceMode)
)

const handleGoToPlans = (planId: string) => {
  navigateTo('/plans', { query: { planId } })
}

const loadSanityModeOptions = async () => {
  try {
    const response = await Service.getPlanComboxApiInfoComboxPlanPost({
      consumer: PlanComboxIn.consumer.MAAEND,
    })
    if (response?.code === 200 && response.data) {
      sanityModeOptions.value = response.data
        .filter((item): item is ComboBoxItem & { value: string } => item.value !== null)
        .map(item => ({ label: item.label, value: item.value }))
    }
  } catch (error) {
    logger.error(`加载理智任务计划失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

const loadSanityPlan = async (planId: string, kind: 'protocol' | 'essence') => {
  const version = ++planLoadVersion[kind]
  const config = kind === 'protocol' ? planModeConfig : essencePlanConfig
  const currentMode = () =>
    kind === 'protocol' ? formData.Info.SanityMode : formData.Info.AutoEssenceMode
  if (
    !planId ||
    ['Fixed', 'Native'].includes(planId) ||
    (kind === 'protocol' && formData.Info.SanityStrategy !== 'MAS')
  ) {
    config.value = null
    return
  }

  try {
    const response = await getPlans(planId)
    // 已切换到其他计划表：丢弃过期响应，避免旧数据覆盖当前 UI
    if (version !== planLoadVersion[kind] || currentMode() !== planId) {
      return
    }
    const planData = response.data?.[planId] as unknown as Record<string, unknown> | undefined
    const planIndex = response.index?.find(item => item.uid === planId)
    if (planIndex?.type !== PLAN_CONFIG_TYPES.MAA_END || !planData) {
      config.value = null
      return
    }
    const dayKey = MAAEND_PLAN_WEEKDAY_KEYS[(getWeekdayInTimezone(4) + 6) % 7]
    const info = planData.Info as Record<string, unknown> | undefined
    let group = info?.Mode === 'Weekly' ? dayKey : 'ALL'
    if (info?.Mode === 'Rotate') {
      const ordinal = Math.floor((Date.now() + 4 * 3600_000) / 86_400_000) + 719163
      group = `Day${(ordinal % clampRotateDays(info.RotateDays)) + 1}`
    }
    const dayConfig = planData[group]
    config.value = maaEndPlanKeyToSanityConfig(dayConfig)
  } catch (error) {
    if (version !== planLoadVersion[kind]) {
      return
    }
    config.value = null
    logger.error(`加载理智任务计划失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

watch(
  [() => formData.Info.SanityMode, () => formData.Info.SanityStrategy],
  ([value]) => {
    void loadSanityPlan(value, 'protocol')
  },
  { immediate: true }
)
watch(
  () => formData.Info.AutoEssenceMode,
  value => {
    void loadSanityPlan(value, 'essence')
  },
  { immediate: true }
)
onMounted(() => {
  void loadSanityModeOptions()
})
onUnmounted(() => {
  planLoadVersion.protocol++
  planLoadVersion.essence++
})
</script>

<style scoped>
.sanity-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
