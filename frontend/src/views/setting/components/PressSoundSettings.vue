<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { PlayCircleOutlined, QuestionCircleOutlined, UploadOutlined } from '@ant-design/icons-vue'
import type { PressSoundPhase, PressSoundPreset } from '@/types/pressSound'
import type { RadioChangeEvent } from 'ant-design-vue'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'

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
  { label: t('core.setting.pressSound.duck'), value: 'duck' },
  { label: t('core.setting.pressSound.fx1'), value: 'fx1' },
  { label: t('core.setting.pressSound.custom'), value: 'custom' },
])
const fileRows = computed(() => [
  {
    kind: props.preset === 'customPair' ? ('press' as const) : ('single' as const),
    phase: 'press' as const,
    label: t(
      props.preset === 'customPair'
        ? 'core.setting.basic.pressSoundPress'
        : 'core.setting.basic.pressSoundFile'
    ),
    path: props.customPath,
    name: props.customName,
  },
  ...(props.preset === 'customPair'
    ? [
        {
          kind: 'release' as const,
          phase: 'release' as const,
          label: t('core.setting.basic.pressSoundRelease'),
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
      <h3>{{ t('core.setting.basic.pressSoundSection') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :xs="24" :md="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <a-checkbox
              :checked="enabled"
              :disabled="saving"
              :aria-busy="saving"
              @change="(event: CheckboxChangeEvent) => emit('enabledChange', event.target.checked)"
            >
              {{ t('core.setting.basic.pressSoundEnabled') }}
            </a-checkbox>
            <a-tooltip :title="t('core.setting.basic.pressSoundEnabledTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
        </div>
      </a-col>
      <a-col :xs="24" :md="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.basic.pressSoundPreset') }}</span>
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
        <span class="form-label">{{ t('core.setting.basic.pressSoundMode') }}</span>
      </div>
      <a-radio-group
        :value="preset"
        :disabled="saving"
        class="sound-mode"
        @change="(event: RadioChangeEvent) => emit('presetChange', event.target.value)"
      >
        <a-radio-button value="custom">{{ t('core.setting.basic.pressSoundSame') }}</a-radio-button>
        <a-radio-button value="customPair">{{
          t('core.setting.basic.pressSoundSeparate')
        }}</a-radio-button>
      </a-radio-group>
      <p class="sound-help">
        {{
          t(
            preset === 'customPair'
              ? 'core.setting.basic.pressSoundSeparateTip'
              : 'core.setting.basic.pressSoundSameTip'
          )
        }}
      </p>
      <div v-for="file in fileRows" :key="file.kind" class="sound-file-row">
        <span class="sound-file-label">{{ file.label }}</span>
        <a-input
          :value="file.name || file.path.split(/[\\/]/).pop()"
          :placeholder="t('core.setting.basic.pressSoundNoFile')"
          :title="file.path || undefined"
          :aria-label="file.label"
          readonly
          class="sound-file-name"
        />
        <a-button :disabled="saving" @click="emit('import', file.kind)">
          <template #icon><UploadOutlined /></template>
          {{ t('core.setting.basic.pressSoundChooseFile') }}
        </a-button>
        <a-button
          :disabled="saving || !file.path"
          :aria-label="t('core.setting.basic.pressSoundPreviewFile', { name: file.label })"
          @click="emit('preview', file.phase)"
        >
          <template #icon><PlayCircleOutlined /></template>
          {{ t('core.setting.basic.pressSoundPreviewAction') }}
        </a-button>
      </div>
      <p class="sound-help">{{ t('core.setting.basic.pressSoundFileHint') }}</p>
    </div>

    <div class="form-item-vertical">
      <div class="form-label-wrapper">
        <span class="form-label">{{ t('core.setting.basic.pressSoundVolume') }}</span>
      </div>
      <div class="sound-volume-row">
        <a-slider
          :value="volume"
          :min="0"
          :max="1"
          :step="0.05"
          :disabled="saving"
          :aria-label="t('core.setting.basic.pressSoundVolume')"
          class="sound-volume-slider"
          @change="(value: unknown) => emit('volumeChange', value as number)"
        />
        <span class="sound-percent">{{ Math.round(volume * 100) }}%</span>
        <a-button :disabled="saving || !ready" @click="emit('preview')">
          <template #icon><PlayCircleOutlined /></template>
          {{ t('core.setting.basic.pressSoundPreviewPair') }}
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
