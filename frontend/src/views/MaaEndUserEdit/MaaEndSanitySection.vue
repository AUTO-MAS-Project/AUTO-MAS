<template>
  <div class="sanity-section">
    <a-card v-if="formData.Info.IfQuickConfig" id="section-sanity" class="section-card">
      <template #title>{{ t('edit.maaEndSanitySection') }}</template>
      <SanityConfigSection
        :form-data="formData"
        :loading="loading"
        :if-quick-config="formData.Info.IfQuickConfig"
        :crisis-drills-options="crisisDrillsOptions"
        :essence-location-options="essenceLocationOptions"
        :essence-menu-options="essenceMenuOptions"
        :essence-target-weapon-groups="essenceTargetWeaponGroups"
        :options-loading="optionsLoading"
        :options-loaded="optionsLoaded"
        :is-plan-mode="isSanityPlanMode"
        :sanity-mode-options="sanityModeOptions"
        :plan-mode-config="planModeConfig"
        :config-loading="configLoading"
        :show-config-mask="showConfigMask"
        @save="(key, value) => emit('save', key, value)"
        @save-batch="changes => emit('saveBatch', changes)"
        @configure="emit('configure')"
      />
      <a-button
        v-if="formData.Task.IfSanity && isSanityPlanMode && formData.Info.SanityStrategy === 'MAS'"
        type="link"
        class="plans-button"
        @click="handleGoToPlans"
      >
        <template #icon><CalendarOutlined /></template>
        {{ t('edit.goPlan') }}
      </a-button>
    </a-card>

    <a-card
      v-if="
        formData.Info.IfQuickConfig &&
        formData.Task.IfSanity &&
        formData.Info.SanityStrategy === 'Inventory'
      "
      id="section-ims"
      class="section-card"
    >
      <template #title>{{ t('edit.maaEndImsTitle') }}</template>
      <InventoryConfigSection
        :form-data="formData"
        :inventory="inventory"
        :loading="loading"
        :options-loading="optionsLoading"
        @save="(key, value) => emit('save', key, value)"
        @reload="emit('reload')"
      />
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
import {
  MAAEND_PLAN_WEEKDAY_KEYS,
  maaEndPlanKeyToSanityConfig,
  type MaaEndSanityConfig,
  type MaaEndEssenceTargetGroup,
} from '@/utils/maaEndProtocolSpace'
import type { MaaEndUserForm } from './userDefaults'
import InventoryConfigSection from './InventoryConfigSection.vue'
import SanityConfigSection from './SanityConfigSection.vue'

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
  { label: t('edit.fixed'), value: 'Fixed' },
])
const planModeConfig = ref<MaaEndSanityConfig | null>(null)
// 计划表切换版本号：loadSanityPlan 每次调用自增，用于丢弃过期的异步响应
let sanityPlanLoadVersion = 0
const isSanityPlanMode = computed(() => formData.Info.SanityMode !== 'Fixed')

const handleGoToPlans = () => {
  navigateTo('/plans', { query: { planId: formData.Info.SanityMode } })
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

const loadSanityPlan = async (planId: string) => {
  const version = ++sanityPlanLoadVersion

  if (!planId || planId === 'Fixed' || formData.Info.SanityStrategy !== 'MAS') {
    planModeConfig.value = null
    return
  }

  try {
    const response = await getPlans(planId)
    // 已切换到其他计划表：丢弃过期响应，避免旧数据覆盖当前 UI
    if (version !== sanityPlanLoadVersion || formData.Info.SanityMode !== planId) {
      return
    }
    const planData = response.data?.[planId] as unknown as Record<string, unknown> | undefined
    const planIndex = response.index?.find(item => item.uid === planId)
    if (planIndex?.type !== PLAN_CONFIG_TYPES.MAA_END || !planData) {
      planModeConfig.value = null
      return
    }
    const dayKey = MAAEND_PLAN_WEEKDAY_KEYS[(getWeekdayInTimezone(4) + 6) % 7]
    const info = planData.Info as Record<string, unknown> | undefined
    const dayConfig = info?.Mode === 'Weekly' ? planData[dayKey] : planData.ALL
    planModeConfig.value = maaEndPlanKeyToSanityConfig(dayConfig)
  } catch (error) {
    if (version !== sanityPlanLoadVersion) {
      return
    }
    planModeConfig.value = null
    logger.error(`加载理智任务计划失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

watch(
  [() => formData.Info.SanityMode, () => formData.Info.SanityStrategy],
  ([value]) => {
    void loadSanityPlan(value)
  },
  { immediate: true }
)
onMounted(() => {
  void loadSanityModeOptions()
})
onUnmounted(() => {
  sanityPlanLoadVersion++
})
</script>

<style scoped>
.sanity-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
