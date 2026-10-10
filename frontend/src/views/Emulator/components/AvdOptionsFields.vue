<script setup lang="ts">
/**
 * 魔改 AVD 实例的两个选项：内存、气球。显示固定 720p、不带声卡，不是选项；有没有窗口也不是实例选项：
 * 手动启动带窗口，任务拉起跟静默模式走。新建实例与修改已有实例共用这一组表单项，外层负责提交。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { MEMORY_CHOICES_MB, RECOMMENDED_MEMORY_GB, type AvdOptionsForm } from '../avdLogic'

const model = defineModel<AvdOptionsForm>({ required: true })

const { t } = useI18n()

const memoryOptions = computed(() =>
  MEMORY_CHOICES_MB.map(mb => ({ value: mb, label: `${mb / 1024} GB` }))
)

const update = <K extends keyof AvdOptionsForm>(key: K, value: AvdOptionsForm[K]) => {
  model.value = { ...model.value, [key]: value }
}
</script>

<template>
  <div class="avd-options-fields">
    <a-form-item
      :label="t('emulator2.avd.fieldMemory')"
      :extra="t('emulator2.avd.memoryRecommend', RECOMMENDED_MEMORY_GB)"
    >
      <a-select
        :value="model.memoryMb"
        :options="memoryOptions"
        style="width: 200px"
        @update:value="(value: number) => update('memoryMb', value)"
      />
    </a-form-item>
    <a-form-item :label="t('emulator2.avd.fieldBalloon')" :extra="t('emulator2.avd.balloonHint')">
      <a-switch
        :checked="model.balloon"
        @update:checked="(value: boolean) => update('balloon', value)"
      />
    </a-form-item>
  </div>
</template>
