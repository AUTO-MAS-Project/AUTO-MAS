<script setup lang="ts">
/**
 * 新建 ModAVD 实例时的选项：内存、帧率与分辨率。DPI 跟随分辨率档位；有没有窗口
 * 也不是实例选项：手动启动带窗口，任务拉起跟静默模式走。已有实例的内存、帧率在齿轮「实例设置」里改。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  AVD_RESOLUTIONS,
  RESOLUTION_CHOICES,
  type AvdResolution,
  FPS_CHOICES,
  MEMORY_CHOICES_MB,
  RECOMMENDED_MEMORY_GB,
  type AvdOptionsForm,
} from '../avdLogic'

const model = defineModel<AvdOptionsForm>({ required: true })

const { t } = useI18n()

const memoryOptions = computed(() =>
  MEMORY_CHOICES_MB.map(mb => ({ value: mb, label: `${mb / 1024} GB` }))
)
const resolutionOptions = computed(() =>
  RESOLUTION_CHOICES.map(value => ({
    value,
    label: `${value}p (${AVD_RESOLUTIONS[value].width}×${AVD_RESOLUTIONS[value].height})`,
  }))
)
const fpsOptions = computed(() => FPS_CHOICES.map(value => ({ value, label: `${value}` })))

const update = <K extends keyof AvdOptionsForm>(key: K, value: AvdOptionsForm[K]) => {
  model.value = { ...model.value, [key]: value }
}
</script>

<template>
  <div class="avd-options-fields">
    <a-form-item
      :label="t('core.emulator2.fieldResolution')"
      :extra="t('core.emulator2.avd.resolutionHint')"
    >
      <a-select
        :value="model.resolution"
        :options="resolutionOptions"
        style="width: 200px"
        @update:value="(value: AvdResolution) => update('resolution', value)"
      />
    </a-form-item>
    <a-form-item
      :label="t('core.emulator2.avd.fieldMemory')"
      :extra="t('core.emulator2.avd.memoryRecommend', RECOMMENDED_MEMORY_GB)"
    >
      <a-select
        :value="model.memoryMb"
        :options="memoryOptions"
        style="width: 200px"
        @update:value="(value: number) => update('memoryMb', value)"
      />
    </a-form-item>
    <a-form-item :label="t('core.emulator2.fieldFps')">
      <a-select
        :value="model.fps"
        :options="fpsOptions"
        style="width: 200px"
        @update:value="(value: number) => update('fps', value)"
      />
    </a-form-item>
  </div>
</template>
