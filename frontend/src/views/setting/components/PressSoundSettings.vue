<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { PlayCircleOutlined, SoundOutlined, UploadOutlined } from '@ant-design/icons-vue'
import type { PressSoundPhase, PressSoundPreset } from '@/types/pressSound'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'

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
const modeOptions = computed(() => [
  { label: t('core.setting.basic.pressSoundSame'), value: 'custom' },
  { label: t('core.setting.basic.pressSoundSeparate'), value: 'customPair' },
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
  <SectionCard :title="t('core.setting.basic.pressSoundSection')" :icon="SoundOutlined">
    <SettingRow
      :label="t('core.setting.basic.pressSoundEnabled')"
      :hint="t('core.setting.basic.pressSoundEnabledTip')"
    >
      <a-switch
        :checked="enabled"
        :loading="saving"
        :disabled="saving"
        :aria-busy="saving"
        :aria-label="t('core.setting.basic.pressSoundEnabled')"
        @change="(checked: boolean | string | number) => emit('enabledChange', !!checked)"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.basic.pressSoundPreset')"
      :hint="t('core.setting.basic.pressSoundPresetTip')"
    >
      <a-select
        class="preset-select"
        :value="isCustom ? 'custom' : preset"
        :options="soundOptions"
        :disabled="saving"
        :aria-label="t('core.setting.basic.pressSoundPreset')"
        @change="(value: unknown) => emit('presetChange', value as PressSoundPreset)"
      />
    </SettingRow>

    <!-- 自定义音效：模式与逐文件选择都需要整行空间 -->
    <SettingRow
      v-if="isCustom"
      stacked
      :label="t('core.setting.basic.pressSoundMode')"
      :hint="
        t(
          preset === 'customPair'
            ? 'core.setting.basic.pressSoundSeparateTip'
            : 'core.setting.basic.pressSoundSameTip'
        )
      "
    >
      <div class="sound-custom">
        <a-segmented
          :value="preset"
          :options="modeOptions"
          :disabled="saving"
          @change="(value: any) => emit('presetChange', value as PressSoundPreset)"
        />
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
    </SettingRow>

    <SettingRow
      :label="t('core.setting.basic.pressSoundVolume')"
      :hint="t('core.setting.basic.pressSoundVolumeTip')"
    >
      <div class="sound-volume-row">
        <a-slider
          class="sound-volume-slider"
          :value="volume"
          :min="0"
          :max="1"
          :step="0.05"
          :disabled="saving"
          :aria-label="t('core.setting.basic.pressSoundVolume')"
          @change="(value: unknown) => emit('volumeChange', value as number)"
        />
        <span class="sound-percent">{{ Math.round(volume * 100) }}%</span>
        <a-button :disabled="saving || !ready" @click="emit('preview')">
          <template #icon><PlayCircleOutlined /></template>
          {{ t('core.setting.basic.pressSoundPreviewPair') }}
        </a-button>
      </div>
    </SettingRow>
  </SectionCard>
</template>

<style scoped>
.preset-select {
  width: 220px;
}

.sound-custom {
  display: flex;
  width: 100%;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.sound-file-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.sound-file-label {
  width: 48px;
  flex-shrink: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.sound-file-name {
  flex: 1 1 200px;
  min-width: 0;
  max-width: 360px;
  text-overflow: ellipsis;
}

.sound-help {
  margin: 0;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.sound-volume-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  max-width: 480px;
}

.sound-volume-slider {
  flex: 1;
  min-width: 64px;
  margin: 0;
}

.sound-percent {
  min-width: 36px;
  color: var(--ant-color-text);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
</style>
