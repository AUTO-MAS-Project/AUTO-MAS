<script setup lang="ts">
/**
 * 新建魔改 AVD 实例时的选项：内存与帧率。显示固定 720p、不带声卡、气球固定开，不是选项；有没有窗口
 * 也不是实例选项：手动启动带窗口，任务拉起跟静默模式走。已有实例的内存、帧率在齿轮「实例设置」里改。
 */
import { computed } from 'vue'

import {
  FPS_CHOICES,
  MEMORY_CHOICES_MB,
  RECOMMENDED_MEMORY_GB,
  type AvdOptionsForm,
} from '../avdLogic'

const model = defineModel<AvdOptionsForm>({ required: true })

const memoryOptions = computed(() =>
  MEMORY_CHOICES_MB.map(mb => ({ value: mb, label: `${mb / 1024} GB` }))
)
const fpsOptions = computed(() => FPS_CHOICES.map(value => ({ value, label: `${value}` })))

const update = <K extends keyof AvdOptionsForm>(key: K, value: AvdOptionsForm[K]) => {
  model.value = { ...model.value, [key]: value }
}
</script>

<template>
  <div class="avd-options-fields">
    <a-form-item
      :label="$t('emulator2.avd.fieldMemory')"
      :extra="$t('emulator2.avd.memoryRecommend', RECOMMENDED_MEMORY_GB)"
    >
      <a-select
        :value="model.memoryMb"
        :options="memoryOptions"
        style="width: 200px"
        @update:value="(value: number) => update('memoryMb', value)"
      />
    </a-form-item>
    <a-form-item :label="$t('emulator2.fieldFps')">
      <a-select
        :value="model.fps"
        :options="fpsOptions"
        style="width: 200px"
        @update:value="(value: number) => update('fps', value)"
      />
    </a-form-item>
  </div>
</template>
