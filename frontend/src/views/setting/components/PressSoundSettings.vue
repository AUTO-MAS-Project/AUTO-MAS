<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { message } from 'ant-design-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'
import { PlayCircleOutlined, SoundOutlined, UploadOutlined } from '@ant-design/icons-vue'
import {
  MAX_PRESS_SOUND_BYTES,
  type PressSoundPhase,
  type PressSoundPreset,
} from '@/types/pressSound'
import { usePressSoundStore } from '@/stores/pressSound'
import {
  clearCustomSoundCache,
  playPressSound,
  previewPressSound,
} from '@/components/satellite/pressSound'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'

const pressSoundStore = usePressSoundStore()
void pressSoundStore.load()
const {
  enabled,
  preset,
  volume,
  saving,
  customPath,
  customName,
  customReleasePath,
  customReleaseName,
} = storeToRefs(pressSoundStore)
const logger = window.electronAPI.getLogger('设置')

const { t } = useI18n()
const isCustom = computed(() => preset.value === 'custom' || preset.value === 'customPair')
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
    kind: preset.value === 'customPair' ? ('press' as const) : ('single' as const),
    phase: 'press' as const,
    label: t(
      preset.value === 'customPair'
        ? 'core.setting.basic.pressSoundPress'
        : 'core.setting.basic.pressSoundFile'
    ),
    path: customPath.value,
    name: customName.value,
  },
  ...(preset.value === 'customPair'
    ? [
        {
          kind: 'release' as const,
          phase: 'release' as const,
          label: t('core.setting.basic.pressSoundRelease'),
          path: customReleasePath.value,
          name: customReleaseName.value,
        },
      ]
    : []),
])
const ready = computed(() => !isCustom.value || fileRows.value.every(file => Boolean(file.path)))

const reportPressSoundError = (action: string, error: unknown): void => {
  const errorMsg = error instanceof Error ? error.message : String(error)
  logger.error(`${action}失败: ${errorMsg}`)
  message.error(t('core.setting.toast.pressSoundSaveFailed'))
}

const handlePressSoundEnabledChange = async (enabled: boolean) => {
  try {
    await pressSoundStore.persist({ enabled })
  } catch (error) {
    reportPressSoundError('保存按压音效开关', error)
  }
}

const handlePressSoundPresetChange = async (value: SelectValue) => {
  if (typeof value !== 'string') {
    return
  }

  try {
    await pressSoundStore.persist({ preset: value as PressSoundPreset })
  } catch (error) {
    reportPressSoundError('保存按压音效种类', error)
  }
}

const handlePressSoundVolumeChange = async (volume: number) => {
  try {
    await pressSoundStore.persist({ volume })
  } catch (error) {
    reportPressSoundError('保存按压音效音量', error)
  }
}

/** 导入自定义音频：单文件模式导一个，双文件模式分别导按下与松开 */
const handlePressSoundImport = async (kind: 'single' | 'press' | 'release' = 'single') => {
  try {
    const files = await window.electronAPI.selectFile([
      { name: '音频文件', extensions: ['wav', 'mp3', 'ogg', 'm4a', 'aac', 'flac'] },
    ])
    if (files.length === 0) {
      return
    }

    const filePath = files[0]
    // 上限交给主进程把关：超了它只回大小、不读内容，不会为了拒绝而先把整个文件读进内存。
    // 大小用它 stat 出来的真实字节数，不拿 base64 长度反推——那样会把 padding 当成文件内容
    const { base64, size } = await window.electronAPI.readFileBase64(
      filePath,
      MAX_PRESS_SOUND_BYTES
    )
    if (size > MAX_PRESS_SOUND_BYTES) {
      message.error(t('core.setting.toast.pressSoundTooLarge'))
      return
    }
    if (!base64) {
      message.error(t('core.setting.toast.pressSoundReadFailed'))
      return
    }
    // 同一个路径的文件可能被换过内容，缓存里的旧音频要作废
    clearCustomSoundCache(filePath)

    const name = filePath.split(/[\\/]/).pop() ?? filePath
    if (kind === 'single') {
      await pressSoundStore.persist({
        preset: 'custom',
        customPath: filePath,
        customName: name,
        enabled: true,
      })
    } else {
      // 双文件模式：导完第二个才切过去，只有一个文件时先只记路径
      const pressPath = kind === 'press' ? filePath : pressSoundStore.customPath
      const releasePath = kind === 'release' ? filePath : pressSoundStore.customReleasePath
      const ready = Boolean(pressPath && releasePath)
      await pressSoundStore.persist({
        ...(kind === 'press'
          ? { customPath: filePath, customName: name }
          : { customReleasePath: filePath, customReleaseName: name }),
        ...(ready ? { preset: 'customPair' as const, enabled: true } : {}),
      })
    }
    message.success(t('core.setting.toast.pressSoundImported'))
  } catch (error) {
    reportPressSoundError('导入按压音效', error)
  }
}

const handlePressSoundPreview = (phase?: PressSoundPhase) => {
  if (phase) {
    const filePath =
      phase === 'release' ? pressSoundStore.customReleasePath : pressSoundStore.customPath
    if (filePath) {
      void playPressSound({
        preset: 'custom',
        volume: pressSoundStore.volume,
        customPath: filePath,
      })
    }
    return
  }

  const options = {
    preset: pressSoundStore.preset,
    volume: pressSoundStore.volume,
    customPath: pressSoundStore.customPath,
    customReleasePath: pressSoundStore.customReleasePath,
  }
  void previewPressSound(options)
}
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
        @change="(checked: boolean | string | number) => handlePressSoundEnabledChange(!!checked)"
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
        @change="handlePressSoundPresetChange"
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
          @change="handlePressSoundPresetChange"
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
          <a-button :disabled="saving" @click="handlePressSoundImport(file.kind)">
            <template #icon><UploadOutlined /></template>
            {{ t('core.setting.basic.pressSoundChooseFile') }}
          </a-button>
          <a-button
            :disabled="saving || !file.path"
            :aria-label="t('core.setting.basic.pressSoundPreviewFile', { name: file.label })"
            @click="handlePressSoundPreview(file.phase)"
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
          @change="(value: unknown) => handlePressSoundVolumeChange(value as number)"
        />
        <span class="sound-percent">{{ Math.round(volume * 100) }}%</span>
        <a-button :disabled="saving || !ready" @click="handlePressSoundPreview()">
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
