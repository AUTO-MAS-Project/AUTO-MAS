<template>
  <div class="stage-config">
    <!-- 区块内最多一条提示：选项读取失败优先，其次是引擎切换后要重选副本 -->
    <a-alert
      v-if="stageNotice"
      :type="stageNotice.type"
      show-icon
      class="stage-alert"
      :message="stageNotice.message"
    />

    <!-- 副本类型 + 该类型下保存的副本：每类副本各存一项，切换类型时回到该类型之前的选择 -->
    <a-row :gutter="16">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('edit.hsrStageType') }}</span>
          </template>
          <a-select
            :value="activeChannel"
            :disabled="loading"
            :options="channelOptions"
            @change="handleActiveChannelChange"
          />
        </a-form-item>
      </a-col>
      <a-col :span="16">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t(CHANNEL_TIP_KEYS[activeChannel])">
              <span class="form-label">
                {{ t('edit.hsrStage') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="activeStageValue"
            :placeholder="t('edit.skip')"
            show-search
            :filter-option="filterOption"
            :disabled="loading || stageOptionsLoading || !activeCategory"
            :loading="stageOptionsLoading"
            :options="activeStageOptions"
            allow-clear
            @change="handleStageSelectChange"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <!-- 培养目标会接管或兜底所选副本：整行显示，不挤在副本类型那一栏下面 -->
    <a-typography-text v-if="buildTargetHint" type="secondary" class="build-target-hint">
      {{ buildTargetHint }}
    </a-typography-text>

    <a-row :gutter="16">
      <a-col :span="16">
        <a-form-item>
          <template #label>
            <!-- 遗器自动分解提醒放在悬停说明里 -->
            <a-tooltip :title="t('edit.turnAutomaticRelicSalvage')">
              <span class="form-label">
                {{ t('edit.echoOfWar') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="eowSelectValue"
            :placeholder="t('edit.skip')"
            show-search
            :disabled="loading || stageOptionsLoading || !dynamicEowCategory"
            :loading="stageOptionsLoading"
            :filter-option="filterOption"
            :options="eowSelectOptions"
            allow-clear
            @change="handleEowStageChange"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.startDayIfIt')">
              <span class="form-label">
                {{ t('edit.echoOfWarStartDay') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="formData.TaskOpt.EchoOfWarWeekday ?? 'Monday'"
            :disabled="loading"
            :options="eowWeekdayOptions"
            @change="handleEowWeekdayChange"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type {
  HSRDynamicStageCategory,
  HSRDynamicStageOption,
  HSRDynamicStageOptionsData,
  HSRScriptStageContainer,
  HSRScriptStagePayload,
  HSRStageEngine,
  HSRUserConfigData,
} from './types'
import {
  CATEGORY_KEYS_BY_CHANNEL,
  CHANNEL_LABEL_KEYS,
  EOW_WEEKDAY_LABEL_KEYS,
  STAGE_CHANNELS,
  hasLegacyEngineMismatch,
  isEowCategory,
  isStageMissingForEngine,
  readChannelStage,
  readEowStage,
  readStageContainer,
  resolveStageChannel,
  writeEngineStage,
  type HSRStageChannel,
} from './stageState'

const { t } = useI18n()

type StageSectionFormData = Pick<HSRUserConfigData, 'Stage' | 'TaskOpt'>

// 体力模块设置里的副本选择：只读写 Stage / TaskOpt；loading 用于保存中禁用下拉。
const props = defineProps<{
  formData: StageSectionFormData
  loading: boolean
  dailyEngine: HSRStageEngine
  stageOptions: HSRDynamicStageOptionsData | null
  stageOptionsLoading: boolean
  stageOptionsError: string
  /** 引擎显示名（三月七 / SRA），文案里不出现原始代号。 */
  engineLabel: string
  /** 已开启的「培养目标」开关标签；null 表示没开。 */
  buildTargetLabel?: string | null
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

// 各副本类型的说明（原先四个下拉的悬停说明）
const CHANNEL_TIP_KEYS: Record<HSRStageChannel, string> = {
  CalyxGolden: 'edit.calyxGoldenCharacterExp',
  CalyxCrimson: 'edit.calyxCrimsonTraceMaterials',
  Relic: 'edit.cavernsCorrosionRelicDomains',
  Ornament: 'edit.ornamentExtractionPlanarOrnament',
}

const eowWeekdayOptions = computed(() =>
  Object.entries(EOW_WEEKDAY_LABEL_KEYS).map(([value, key]) => ({ value, label: t(key) }))
)

const channelOptions = computed(() =>
  STAGE_CHANNELS.map(channel => ({ value: channel, label: t(CHANNEL_LABEL_KEYS[channel]) }))
)

const activeChannel = computed(() => resolveStageChannel(props.formData?.Stage?.Channel))

const dynamicCategories = computed(() => props.stageOptions?.categories ?? [])

const categoryForChannel = (channel: HSRStageChannel): HSRDynamicStageCategory | null => {
  const keys = CATEGORY_KEYS_BY_CHANNEL[channel]
  return dynamicCategories.value.find(category => keys.includes(category.categoryKey)) ?? null
}

const activeCategory = computed(() => categoryForChannel(activeChannel.value))

const dynamicEowCategory = computed(
  () => dynamicCategories.value.find(category => isEowCategory(category.categoryKey)) ?? null
)

const buildDynamicOptionLabel = (option: HSRDynamicStageOption) =>
  option.detail ? `${option.label} | ${option.detail}` : option.label

const toSelectOptions = (category: HSRDynamicStageCategory | null) =>
  (category?.options ?? []).map(option => ({
    value: option.value,
    label: buildDynamicOptionLabel(option),
  }))

const findDynamicOption = (
  value: unknown,
  category: HSRDynamicStageCategory | null
): HSRDynamicStageOption | null => {
  if (typeof value !== 'string' || !value || !category) return null
  return category.options?.find(item => item.value === value) ?? null
}

const activeStageOptions = computed(() => toSelectOptions(activeCategory.value))

// 下拉只显示当前引擎选项里真实存在的那一项，免得显示一个选不中的旧值
const activeStageValue = computed(
  () =>
    findDynamicOption(
      readChannelStage(props.formData.Stage, props.dailyEngine, activeChannel.value)?.value,
      activeCategory.value
    )?.value
)

const eowSelectOptions = computed(() => toSelectOptions(dynamicEowCategory.value))

const eowSelectValue = computed(
  () =>
    findDynamicOption(
      readEowStage(props.formData.Stage, props.dailyEngine)?.value,
      dynamicEowCategory.value
    )?.value
)

const stageNotice = computed<{ type: 'error' | 'warning'; message: string } | null>(() => {
  if (props.stageOptionsError && !props.stageOptionsLoading) {
    return { type: 'error', message: props.stageOptionsError }
  }
  if (hasLegacyEngineMismatch(props.formData.Stage, props.dailyEngine)) {
    return { type: 'warning', message: t('edit.sanityScriptChangedPick') }
  }
  if (isStageMissingForEngine(props.formData.Stage, props.dailyEngine)) {
    return {
      type: 'warning',
      message: t('edit.hsrStageMissingForEngine', { engine: props.engineLabel }),
    }
  }
  return null
})

// 开了培养目标时，这里选的副本只作兜底（三月七）或被忽略（SRA：MAS 会清空 tasklist）
const buildTargetHint = computed(() => {
  if (!props.buildTargetLabel) return undefined
  return props.dailyEngine === 'SRA'
    ? t('edit.hsrBuildTargetIgnoredSra', { label: props.buildTargetLabel })
    : t('edit.hsrBuildTargetFallbackM7a', { label: props.buildTargetLabel })
})

const buildNativeStagePayload = (option: HSRDynamicStageOption): HSRScriptStagePayload => ({
  engine: props.dailyEngine,
  category: option.categoryKey,
  categoryLabel: option.categoryLabel,
  label: option.label,
  detail: option.detail ?? '',
  value: option.value,
  sra: option.sra
    ? {
        id: option.sra.id ?? '',
        level: option.sra.level ?? null,
      }
    : undefined,
  m7a: option.m7a
    ? {
        instanceType: option.m7a.instanceType ?? '',
        instanceName: option.m7a.instanceName ?? '',
      }
    : undefined,
})

const saveNativeMainStage = (channel: HSRStageChannel, option: HSRDynamicStageOption | null) => {
  const container = readStageContainer(props.formData.Stage, props.dailyEngine)
  const stages: Partial<Record<HSRStageChannel, HSRScriptStagePayload>> = {}

  if (container?.stages) {
    for (const item of STAGE_CHANNELS) {
      const payload = container.stages[item]
      if (payload) stages[item] = payload
    }
  }

  if (option) stages[channel] = buildNativeStagePayload(option)
  else delete stages[channel]

  const currentValue: HSRScriptStageContainer | null = Object.keys(stages).length
    ? { engine: props.dailyEngine, stages }
    : null
  emit(
    'save',
    'Stage.ScriptStage',
    writeEngineStage(props.formData.Stage.ScriptStage, props.dailyEngine, currentValue)
  )
}

const handleStageSelectChange = (value: unknown) => {
  const category = activeCategory.value
  if (!category) return
  saveNativeMainStage(activeChannel.value, findDynamicOption(value, category))
}

const handleEowStageChange = (value: unknown) => {
  const category = dynamicEowCategory.value
  if (!category) return
  const option = findDynamicOption(value, category)
  emit(
    'save',
    'Stage.ScriptEchoOfWar',
    writeEngineStage<HSRScriptStagePayload>(
      props.formData.Stage.ScriptEchoOfWar,
      props.dailyEngine,
      option ? buildNativeStagePayload(option) : null
    )
  )
}

const handleActiveChannelChange = (value: HSRStageChannel) => {
  if (activeChannel.value === value) return
  emit('save', 'Stage.Channel', value)
}

const handleEowWeekdayChange = (value: string) => {
  emit('save', 'TaskOpt.EchoOfWarWeekday', value)
}

const filterOption = (input: unknown, option?: { label?: unknown; children?: unknown }) => {
  const text = (option?.label ?? option?.children ?? '').toString()
  return text.toLowerCase().includes(String(input ?? '').toLowerCase())
}
</script>

<style scoped>
.stage-config {
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.stage-alert {
  margin-bottom: 12px;
}

.build-target-hint {
  display: block;
  margin: -12px 0 16px;
  font-size: 13px;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}
</style>
