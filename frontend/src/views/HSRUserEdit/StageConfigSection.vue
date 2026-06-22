<template>
  <div class="form-section">
    <div class="section-header">
      <h3>体力配置</h3>
    </div>

    <a-alert
      v-if="nativeEngineMismatch"
      type="warning"
      show-icon
      style="margin-bottom: 8px"
      message="体力执行脚本已切换，请重新选择副本。"
    />
    <a-alert
      v-if="stageOptionsError && !stageOptionsLoading"
      type="error"
      show-icon
      style="margin-bottom: 8px"
      :message="stageOptionsError"
    />

    <!-- 第一行：四个独立关卡下拉框。选项只来自当前执行脚本暴露的副本配置。 -->
    <a-row :gutter="24">
      <a-col :span="6">
        <a-form-item>
          <template #label>
            <a-tooltip title="拟造花萼（金）：角色经验 / 光锥经验 / 信用点">
              <span class="form-label">
                拟造花萼（金）
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="stageValueByChannel.CalyxGolden"
            size="large"
            placeholder="不刷"
            show-search
            :filter-option="filterOption"
            :disabled="isStageSelectDisabled('CalyxGolden')"
            :loading="stageOptionsLoading"
            :options="stageOptionsByChannel.CalyxGolden"
            allow-clear
            @change="value => handleStageSelectChange('CalyxGolden', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item>
          <template #label>
            <a-tooltip title="拟造花萼（赤）：行迹材料（金/赤互不覆盖，可同时保存）">
              <span class="form-label">
                拟造花萼（赤）
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="stageValueByChannel.CalyxCrimson"
            size="large"
            placeholder="不刷"
            show-search
            :filter-option="filterOption"
            :disabled="isStageSelectDisabled('CalyxCrimson')"
            :loading="stageOptionsLoading"
            :options="stageOptionsByChannel.CalyxCrimson"
            allow-clear
            @change="value => handleStageSelectChange('CalyxCrimson', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item>
          <template #label>
            <a-tooltip title="侵蚀隧洞：遗器副本">
              <span class="form-label">
                侵蚀隧洞
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="stageValueByChannel.Relic"
            size="large"
            placeholder="不刷"
            show-search
            :filter-option="filterOption"
            :disabled="isStageSelectDisabled('Relic')"
            :loading="stageOptionsLoading"
            :options="stageOptionsByChannel.Relic"
            allow-clear
            @change="value => handleStageSelectChange('Relic', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item>
          <template #label>
            <a-tooltip title="饰品提取：位面饰品副本">
              <span class="form-label">
                饰品提取
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="stageValueByChannel.Ornament"
            size="large"
            placeholder="不刷"
            show-search
            :filter-option="filterOption"
            :disabled="isStageSelectDisabled('Ornament')"
            :loading="stageOptionsLoading"
            :options="stageOptionsByChannel.Ornament"
            allow-clear
            @change="value => handleStageSelectChange('Ornament', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第二行：刷取副本 + 当前生效关卡 -->
    <a-row :gutter="24" style="margin-top: 8px">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="选择要刷取的副本；本字段会写入 Stage.Channel。">
              <span class="form-label">
                刷取副本
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="activeChannel"
            size="large"
            :disabled="loading"
            :options="activeChannelOptions"
            @change="handleActiveChannelChange"
          />
        </a-form-item>
      </a-col>
      <a-col :span="16">
        <a-form-item>
          <template #label>
            <span class="form-label">当前生效关卡</span>
          </template>
          <div class="current-stage-display">
            <a-tag :color="currentStageColor" size="large" class="stage-tag">
              {{ currentStageDisplay }}
            </a-tag>
          </div>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第三行：历战余响 | 历战余响开始日 -->
    <a-row :gutter="24" style="margin-top: 8px">
      <a-col :span="12">
        <a-form-item name="EchoOfWar">
          <template #label>
            <a-tooltip title="选择要挑战的历战余响关卡。">
              <span class="form-label">
                历战余响
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="eowSelectValue"
            size="large"
            placeholder="不刷"
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
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip
              title="到达开始日且本周未完成时，MAS 会交给 M7A/SRA 尝试完成历战余响；日志确认完成后本周不再执行。"
            >
              <span class="form-label">
                历战余响开始日
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="formData.TaskOpt.EchoOfWarWeekday ?? 'Monday'"
            size="large"
            :disabled="loading"
            :options="EOW_WEEKDAY_OPTIONS"
            @change="handleEowWeekdayChange"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 刷取提示 -->
    <a-alert
      type="info"
      show-icon
      style="margin-top: 8px"
      message="建议在游戏内开启结算遗器自动分解，以免刷取遗器时背包满导致流程中断。"
    />
  </div>
</template>

<script setup lang="ts">
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
} from '@/views/HSRUserEdit/types'

const EOW_WEEKDAY_OPTIONS: { value: string; label: string }[] = [
  { value: 'Monday', label: '周一' },
  { value: 'Tuesday', label: '周二' },
  { value: 'Wednesday', label: '周三' },
  { value: 'Thursday', label: '周四' },
  { value: 'Friday', label: '周五' },
  { value: 'Saturday', label: '周六' },
  { value: 'Sunday', label: '周日' },
]

type StageSectionFormData = Pick<HSRUserConfigData, 'Stage' | 'TaskOpt'>

// HSR 专用：体力配置只读写 Stage / TaskOpt；loading 用于保存中禁用下拉，避免重复点击被父级 isSaving guard 吞掉。
const props = defineProps<{
  formData: StageSectionFormData
  loading: boolean
  dailyEngine: HSRStageEngine
  stageOptions: HSRDynamicStageOptionsData | null
  stageOptionsLoading: boolean
  stageOptionsError: string
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

const emitSave = (key: string, value: unknown) => {
  emit('save', key, value)
}

type ActiveChannel = 'CalyxGolden' | 'CalyxCrimson' | 'Relic' | 'Ornament'

const emptyNativeStageValue = '{ }'

const parseScriptStage = (raw: unknown): HSRScriptStagePayload | null => {
  if (!raw || typeof raw !== 'string') return null
  const text = raw.trim()
  if (!text || text === '{}' || text === '{ }') return null
  try {
    const data = JSON.parse(text)
    return data && typeof data === 'object' && !Array.isArray(data)
      ? (data as HSRScriptStagePayload)
      : null
  } catch {
    return null
  }
}

const payloadMatchesEngine = (payload: HSRScriptStagePayload | null) => {
  return payload?.engine === props.dailyEngine
}

const scriptStageContainer = computed<HSRScriptStageContainer | null>(() => {
  const payload = parseScriptStage(
    props.formData.Stage.ScriptStage
  ) as HSRScriptStageContainer | null
  if (!payload?.stages || payload.engine !== props.dailyEngine) return null
  return payload
})

const isEowCategory = (categoryKey: string) => {
  return categoryKey === 'echo_of_war' || categoryKey === '历战余响'
}

const dynamicCategories = computed(() => props.stageOptions?.categories ?? [])

const activeChannels: ActiveChannel[] = ['CalyxGolden', 'CalyxCrimson', 'Relic', 'Ornament']

const categoryKeysByChannel: Record<ActiveChannel, string[]> = {
  CalyxGolden: ['calyx_golden', '拟造花萼（金）'],
  CalyxCrimson: ['calyx_crimson', '拟造花萼（赤）'],
  Relic: ['caver_of_corrosion', '侵蚀隧洞'],
  Ornament: ['ornament_extraction', '饰品提取'],
}

const dynamicCategoryByChannel = computed<Record<ActiveChannel, HSRDynamicStageCategory | null>>(
  () => {
    const findCategory = (channel: ActiveChannel) => {
      const keys = categoryKeysByChannel[channel]
      return dynamicCategories.value.find(category => keys.includes(category.categoryKey)) ?? null
    }
    return {
      CalyxGolden: findCategory('CalyxGolden'),
      CalyxCrimson: findCategory('CalyxCrimson'),
      Relic: findCategory('Relic'),
      Ornament: findCategory('Ornament'),
    }
  }
)

const dynamicEowCategory = computed(() => {
  return dynamicCategories.value.find(category => isEowCategory(category.categoryKey)) ?? null
})

const selectedEowPayload = computed(() => parseScriptStage(props.formData.Stage.ScriptEchoOfWar))

const nativeEngineMismatch = computed(() => {
  const main = parseScriptStage(props.formData.Stage.ScriptStage) as HSRScriptStageContainer | null
  const eow = selectedEowPayload.value
  return (
    (!!main?.engine && main.engine !== props.dailyEngine) ||
    (!!eow?.engine && eow.engine !== props.dailyEngine)
  )
})

const buildDynamicOptionLabel = (option: HSRDynamicStageOption) => {
  return option.detail ? `${option.label} | ${option.detail}` : option.label
}

const findDynamicOption = (
  value: unknown,
  categories: HSRDynamicStageCategory[]
): HSRDynamicStageOption | null => {
  if (typeof value !== 'string' || !value) return null
  for (const category of categories) {
    const option = category.options?.find(item => item.value === value)
    if (option) return option
  }
  return null
}

const buildNativeStagePayload = (option: HSRDynamicStageOption): HSRScriptStagePayload => {
  return {
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
  }
}

const getPayloadForChannel = (channel: ActiveChannel): HSRScriptStagePayload | null => {
  const container = scriptStageContainer.value
  const directPayload = container?.stages?.[channel]
  return payloadMatchesEngine(directPayload ?? null) ? (directPayload ?? null) : null
}

const selectedDynamicOptionForChannel = (channel: ActiveChannel) => {
  const category = dynamicCategoryByChannel.value[channel]
  const payload = getPayloadForChannel(channel)
  if (!category || !payload) return null
  return findDynamicOption(payload?.value, [category])
}

const dynamicOptionsForChannel = (channel: ActiveChannel) => {
  const category = dynamicCategoryByChannel.value[channel]
  return (category?.options ?? []).map(option => ({
    value: option.value,
    label: buildDynamicOptionLabel(option),
  }))
}

const isStageSelectDisabled = (channel: ActiveChannel) => {
  return props.loading || props.stageOptionsLoading || !dynamicCategoryByChannel.value[channel]
}

const stageOptionsByChannel = computed<Record<ActiveChannel, { value: string; label: string }[]>>(
  () => ({
    CalyxGolden: dynamicOptionsForChannel('CalyxGolden'),
    CalyxCrimson: dynamicOptionsForChannel('CalyxCrimson'),
    Relic: dynamicOptionsForChannel('Relic'),
    Ornament: dynamicOptionsForChannel('Ornament'),
  })
)

const stageValueByChannel = computed<Record<ActiveChannel, string | undefined>>(() => ({
  CalyxGolden: selectedDynamicOptionForChannel('CalyxGolden')?.value,
  CalyxCrimson: selectedDynamicOptionForChannel('CalyxCrimson')?.value,
  Relic: selectedDynamicOptionForChannel('Relic')?.value,
  Ornament: selectedDynamicOptionForChannel('Ornament')?.value,
}))

const saveNativeMainStage = (channel: ActiveChannel, option: HSRDynamicStageOption | null) => {
  const container = scriptStageContainer.value
  const stages: Partial<Record<ActiveChannel, HSRScriptStagePayload>> = {}

  if (container?.stages) {
    for (const item of activeChannels) {
      const payload = container.stages[item]
      if (payload) stages[item] = payload
    }
  }

  if (option) {
    stages[channel] = buildNativeStagePayload(option)
  } else {
    delete stages[channel]
  }

  const value = Object.keys(stages).length
    ? JSON.stringify({ engine: props.dailyEngine, stages })
    : emptyNativeStageValue

  emitSave('Stage.ScriptStage', value)
}

const saveNativeEchoOfWarStage = (option: HSRDynamicStageOption | null) => {
  const value = option ? JSON.stringify(buildNativeStagePayload(option)) : emptyNativeStageValue
  emitSave('Stage.ScriptEchoOfWar', value)
}

const handleStageSelectChange = (channel: ActiveChannel, value: unknown) => {
  const category = dynamicCategoryByChannel.value[channel]
  if (category) {
    const option = findDynamicOption(value, [category])
    saveNativeMainStage(channel, option)
  }
}

const eowDynamicOptions = computed(() => {
  return (dynamicEowCategory.value?.options ?? []).map(option => ({
    value: option.value,
    label: buildDynamicOptionLabel(option),
  }))
})

const selectedEowOption = computed(() => {
  const payload = selectedEowPayload.value
  if (!payloadMatchesEngine(payload)) return null
  const category = dynamicEowCategory.value
  if (!category) return null
  return findDynamicOption(payload?.value, [category])
})

const eowSelectOptions = computed(() => {
  return eowDynamicOptions.value
})

const eowSelectValue = computed(() => {
  return selectedEowOption.value?.value
})

const handleEowStageChange = (value: unknown) => {
  if (dynamicEowCategory.value) {
    const option = findDynamicOption(value, [dynamicEowCategory.value])
    saveNativeEchoOfWarStage(option)
  }
}

const activeChannel = computed<ActiveChannel>(() => {
  const ch = props.formData?.Stage?.Channel
  if (ch === 'CalyxGolden' || ch === 'CalyxCrimson' || ch === 'Relic' || ch === 'Ornament') {
    return ch
  }
  return 'CalyxGolden'
})

// 刷取副本下拉的可见选项（4 类）
const activeChannelOptions = [
  { value: 'CalyxGolden', label: '拟造花萼（金）' },
  { value: 'CalyxCrimson', label: '拟造花萼（赤）' },
  { value: 'Relic', label: '侵蚀隧洞' },
  { value: 'Ornament', label: '饰品提取' },
]

// 当前生效关卡读取：根据 activeChannel 读对应字段
const currentNativePayload = computed(() => {
  return getPayloadForChannel(activeChannel.value)
})

// 当前生效关卡显示：副本类型 + 关卡名
// 格式：拟造花萼（金） 材料：武器经验（以太之蕾 翁法罗斯）
const currentStageDisplay = computed((): string => {
  if (nativeEngineMismatch.value) return '请重新选择副本'
  const nativePayload = currentNativePayload.value
  if (nativePayload?.label) {
    return nativePayload.categoryLabel
      ? `${nativePayload.categoryLabel} ${nativePayload.label}`
      : nativePayload.label
  }
  return '未配置'
})

const currentStageColor = computed((): string => {
  const dynamicCategory = currentNativePayload.value?.category ?? ''
  if (dynamicCategory === '侵蚀隧洞' || dynamicCategory === 'caver_of_corrosion') return 'purple'
  if (dynamicCategory === '饰品提取' || dynamicCategory === 'ornament_extraction') return 'cyan'
  if (dynamicCategory === '拟造花萼（金）' || dynamicCategory === 'calyx_golden') return 'gold'
  if (dynamicCategory === '拟造花萼（赤）' || dynamicCategory === 'calyx_crimson') return 'red'
  return 'default'
})

// 刷取副本
const handleActiveChannelChange = (value: ActiveChannel) => {
  if (activeChannel.value === value) return
  emitSave('Stage.Channel', value)
}

const handleEowWeekdayChange = (value: string) => {
  emitSave('TaskOpt.EchoOfWarWeekday', value)
}

const filterOption = (
  input: unknown,
  option?: { label?: unknown; children?: unknown }
) => {
  const text = (option?.label ?? option?.children ?? '').toString()
  return text.toLowerCase().includes(String(input ?? '').toLowerCase())
}
</script>

<style scoped>
/* 与 HSRUserEdit.vue 主页面 section-header 保持一致：加粗标题 + 分割线 + before 装饰 */
.section-header {
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 22px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.current-stage-display {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
}
.stage-tag {
  font-size: 14px;
  padding: 4px 12px;
}
</style>
