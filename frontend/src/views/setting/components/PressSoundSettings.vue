<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { PlayCircleOutlined, QuestionCircleOutlined, UploadOutlined } from '@ant-design/icons-vue'
import type { PressSoundPhase, PressSoundPreset } from '@/types/pressSound'
import type { RadioChangeEvent } from 'ant-design-vue'

const props = defineProps<{
  enabled: boolean
  preset: PressSoundPreset
  volume: number
  saving: boolean
  customPath: string
  customName: string
  customReleasePath: string
  customReleaseName: string
}>()

const emit = defineEmits<{
  enabledChange: [enabled: boolean]
  presetChange: [preset: PressSoundPreset]
  volumeChange: [volume: number]
  import: [kind: 'single' | 'press' | 'release']
  preview: [phase?: PressSoundPhase]
}>()

const { t } = useI18n()
const isCustom = computed(() => props.preset === 'custom' || props.preset === 'customPair')
const soundOptions = computed(() => [
  { label: t('setting.pressSound.duck'), value: 'duck' },
  { label: t('setting.pressSound.fx1'), value: 'fx1' },
  { label: t('setting.pressSound.custom'), value: 'custom' },
])
const fileRows = computed(() => [
  {
    kind: props.preset === 'customPair' ? ('press' as const) : ('single' as const),
    phase: 'press' as const,
    label: t(
      props.preset === 'customPair'
        ? 'setting.basic.pressSoundPress'
        : 'setting.basic.pressSoundFile'
    ),
    path: props.customPath,
    name: props.customName,
  },
  ...(props.preset === 'customPair'
    ? [
        {
          kind: 'release' as const,
          phase: 'release' as const,
          label: t('setting.basic.pressSoundRelease'),
          path: props.customReleasePath,
          name: props.customReleaseName,
        },
      ]
    : []),
])
const ready = computed(() => !isCustom.value || fileRows.value.every(file => Boolean(file.path)))
</script>

<template>
  <div class="form-section press-sound-settings">
    <div class="section-header">
      <h3>{{ t('setting.basic.pressSoundSection') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :xs="24" :md="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.basic.pressSoundEnabled') }}</span>
            <a-tooltip :title="t('setting.basic.pressSoundEnabledTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-select
            :value="enabled"
            :disabled="saving"
            size="large"
            style="width: 100%"
            @change="(value: unknown) => emit('enabledChange', value === true)"
          >
            <a-select-option :value="true">{{ t('common.on') }}</a-select-option>
            <a-select-option :value="false">{{ t('common.off') }}</a-select-option>
          </a-select>
        </div>
      </a-col>
      <a-col :xs="24" :md="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.basic.pressSoundPreset') }}</span>
          </div>
          <a-select
            :value="isCustom ? 'custom' : preset"
            :options="soundOptions"
            :disabled="saving"
            size="large"
            style="width: 100%"
            @change="(value: unknown) => emit('presetChange', value as PressSoundPreset)"
          />
        </div>
      </a-col>
    </a-row>

    <div v-if="isCustom" class="form-item-vertical">
      <div class="form-label-wrapper">
        <span class="form-label">{{ t('setting.basic.pressSoundMode') }}</span>
      </div>
      <a-radio-group
        :value="preset"
        :disabled="saving"
        class="sound-mode"
        @change="(event: RadioChangeEvent) => emit('presetChange', event.target.value)"
      >
        <a-radio-button value="custom">{{ t('setting.basic.pressSoundSame') }}</a-radio-button>
        <a-radio-button value="customPair">{{
          t('setting.basic.pressSoundSeparate')
        }}</a-radio-button>
      </a-radio-group>
      <p class="sound-help">
        {{
          t(
            preset === 'customPair'
              ? 'setting.basic.pressSoundSeparateTip'
              : 'setting.basic.pressSoundSameTip'
          )
        }}
      </p>
      <div v-for="file in fileRows" :key="file.kind" class="sound-file-row">
        <span class="sound-file-label">{{ file.label }}</span>
        <a-input
          :value="file.name || file.path.split(/[\\/]/).pop()"
          :placeholder="t('setting.basic.pressSoundNoFile')"
          :title="file.path || undefined"
          :aria-label="file.label"
          readonly
          class="sound-file-name"
        />
        <a-button :disabled="saving" @click="emit('import', file.kind)">
          <template #icon><UploadOutlined /></template>
          {{ t('setting.basic.pressSoundChooseFile') }}
        </a-button>
        <a-button
          :disabled="saving || !file.path"
          :aria-label="t('setting.basic.pressSoundPreviewFile', { name: file.label })"
          @click="emit('preview', file.phase)"
        >
          <template #icon><PlayCircleOutlined /></template>
          {{ t('setting.basic.pressSoundPreviewAction') }}
        </a-button>
      </div>
      <p class="sound-help">{{ t('setting.basic.pressSoundFileHint') }}</p>
    </div>

    <div class="form-item-vertical">
      <div class="form-label-wrapper">
        <span class="form-label">{{ t('setting.basic.pressSoundVolume') }}</span>
      </div>
      <div class="sound-volume-row">
        <a-slider
          :value="volume"
          :min="0"
          :max="1"
          :step="0.05"
          :disabled="saving"
          :aria-label="t('setting.basic.pressSoundVolume')"
          class="sound-volume-slider"
          @change="(value: unknown) => emit('volumeChange', value as number)"
        />
        <span class="sound-percent">{{ Math.round(volume * 100) }}%</span>
        <a-button :disabled="saving || !ready" @click="emit('preview')">
          <template #icon><PlayCircleOutlined /></template>
          {{ t('setting.basic.pressSoundPreviewPair') }}
        </a-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sound-mode {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 0;
}

.sound-file-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.sound-file-label {
  width: 48px;
  flex-shrink: 0;
}

.sound-file-name {
  flex: 1 1 160px;
  min-width: 0;
  text-overflow: ellipsis;
}

.sound-help {
  color: var(--ant-color-text-secondary);
  margin: 8px 0 0;
  font-size: 12px;
}

.sound-volume-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.sound-volume-slider {
  flex: 1;
  min-width: 64px;
  max-width: 360px;
}

.sound-percent {
  min-width: 36px;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
</style>
