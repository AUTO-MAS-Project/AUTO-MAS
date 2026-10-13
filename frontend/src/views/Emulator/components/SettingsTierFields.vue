<script setup lang="ts">
/**
 * 实例设置的四个档位下拉：分辨率、帧率、CPU 核数、内存。单台设置与批量设置共用，外层负责提交。
 *
 * 魔改 AVD 的分辨率与帧率固定：单台设置里显示并禁用（``showFixed``），批量设置里不出现。
 * ``snapped`` 里有值的项是打开时被对齐过的，在该项下面用一行小字标出实际值。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { RECOMMENDED_MEMORY_GB } from '../avdLogic'
import {
  RESOLUTION_TIERS,
  STANDARD_TIERS,
  memoryText,
  resolutionText,
  tiersOf,
  type SnappedActual,
  type TierForm,
  type TierKind,
} from '../settingsTiers'

const model = defineModel<TierForm>({ required: true })
const props = withDefaults(
  defineProps<{
    kind: TierKind
    snapped?: SnappedActual | null
    /** 魔改 AVD 固定的分辨率与帧率要不要显示出来（禁用） */
    showFixed?: boolean
    /** 允许清空回「保持原样」（批量设置用） */
    clearable?: boolean
  }>(),
  { snapped: null, showFixed: false, clearable: false }
)

const { t } = useI18n()

const isAvd = computed(() => props.kind === 'avd')
const showResolutionAndFps = computed(() => !isAvd.value || props.showFixed)

const resolutionOptions = computed(() =>
  RESOLUTION_TIERS.map(tier => ({ value: tier, label: resolutionText(tier) }))
)
const fpsOptions = computed(() => STANDARD_TIERS.fps.map(value => ({ value, label: `${value}` })))
const cpuOptions = computed(() =>
  tiersOf(props.kind).cpu.map(value => ({ value, label: `${value}` }))
)
const memoryOptions = computed(() =>
  tiersOf(props.kind).memoryMb.map(value => ({ value, label: memoryText(value) }))
)

const resolutionNote = computed(() => {
  const snapped = props.snapped
  if (!snapped) return ''
  const parts: string[] = []
  if (snapped.resolution) parts.push(`${snapped.resolution.width}×${snapped.resolution.height}`)
  if (snapped.dpi !== null) parts.push(`DPI ${snapped.dpi}`)
  return parts.length ? t('emulator2.tierActual', { value: parts.join(' · ') }) : ''
})

const note = (value: number | null | undefined, format: (v: number) => string = String) =>
  value === null || value === undefined ? '' : t('emulator2.tierActual', { value: format(value) })

const update = <K extends keyof TierForm>(key: K, value: TierForm[K] | undefined) => {
  model.value = { ...model.value, [key]: value ?? null }
}
</script>

<template>
  <a-row :gutter="12">
    <a-col v-if="showResolutionAndFps" :span="12">
      <a-form-item :label="t('emulator2.fieldResolution')">
        <a-select
          :value="model.resolution ?? undefined"
          :options="resolutionOptions"
          :disabled="isAvd"
          :allow-clear="clearable"
          :placeholder="t('emulator2.keepCurrent')"
          size="large"
          style="width: 100%"
          @update:value="(value: TierForm['resolution']) => update('resolution', value)"
        />
        <div v-if="resolutionNote" class="tier-actual">{{ resolutionNote }}</div>
      </a-form-item>
    </a-col>
    <a-col v-if="showResolutionAndFps" :span="12">
      <a-form-item :label="t('emulator2.fieldFps')">
        <a-select
          :value="model.fps ?? undefined"
          :options="fpsOptions"
          :disabled="isAvd"
          :allow-clear="clearable"
          :placeholder="t('emulator2.keepCurrent')"
          size="large"
          style="width: 100%"
          @update:value="(value: number) => update('fps', value)"
        />
        <div v-if="note(snapped?.fps)" class="tier-actual">{{ note(snapped?.fps) }}</div>
      </a-form-item>
    </a-col>
    <a-col :span="12">
      <a-form-item :label="t('emulator2.fieldCpu')">
        <a-select
          :value="model.cpu ?? undefined"
          :options="cpuOptions"
          :allow-clear="clearable"
          :placeholder="t('emulator2.keepCurrent')"
          size="large"
          style="width: 100%"
          @update:value="(value: number) => update('cpu', value)"
        />
        <div v-if="note(snapped?.cpu)" class="tier-actual">{{ note(snapped?.cpu) }}</div>
      </a-form-item>
    </a-col>
    <a-col :span="12">
      <a-form-item
        :label="t('emulator2.fieldMemory')"
        :extra="isAvd ? t('emulator2.avd.memoryRecommend', RECOMMENDED_MEMORY_GB) : undefined"
      >
        <a-select
          :value="model.memoryMb ?? undefined"
          :options="memoryOptions"
          :allow-clear="clearable"
          :placeholder="t('emulator2.keepCurrent')"
          size="large"
          style="width: 100%"
          @update:value="(value: number) => update('memoryMb', value)"
        />
        <div v-if="note(snapped?.memoryMb, memoryText)" class="tier-actual">
          {{ note(snapped?.memoryMb, memoryText) }}
        </div>
      </a-form-item>
    </a-col>
  </a-row>
</template>

<style scoped>
.tier-actual {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
