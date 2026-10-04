<script setup lang="ts">
/**
 * 官方模拟器实例的五个选项：分辨率、内存、气球、GuestAngle、无头。
 * 新建实例与修改已有实例共用这一组表单项，外层负责提交。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { MEMORY_AUTO, MEMORY_CHOICES_MB, type AvdOptionsForm } from '../avdLogic'

const model = defineModel<AvdOptionsForm>({ required: true })

const { t } = useI18n()

const memoryOptions = computed(() => [
  { value: MEMORY_AUTO, label: t('emulator2.avd.memoryAuto') },
  ...MEMORY_CHOICES_MB.map(mb => ({ value: mb, label: `${mb / 1024} GB` })),
])

const update = <K extends keyof AvdOptionsForm>(key: K, value: AvdOptionsForm[K]) => {
  model.value = { ...model.value, [key]: value }
}
</script>

<template>
  <div class="avd-options-fields">
    <a-form-item
      :label="t('emulator2.avd.fieldResolution')"
      :extra="t('emulator2.avd.resolutionHint')"
    >
      <a-radio-group
        :value="model.resolution"
        button-style="solid"
        @update:value="(value: AvdOptionsForm['resolution']) => update('resolution', value)"
      >
        <a-radio-button value="720">720p</a-radio-button>
        <a-radio-button value="1080">1080p</a-radio-button>
      </a-radio-group>
    </a-form-item>
    <a-form-item
      :label="t('emulator2.avd.fieldMemory')"
      :extra="model.memoryMb === MEMORY_AUTO ? t('emulator2.avd.memoryAutoHint') : ''"
    >
      <a-select
        :value="model.memoryMb"
        :options="memoryOptions"
        style="width: 200px"
        @update:value="(value: number) => update('memoryMb', value)"
      />
    </a-form-item>
    <a-row :gutter="12">
      <a-col :span="8">
        <a-form-item
          :label="t('emulator2.avd.fieldBalloon')"
          :extra="t('emulator2.avd.balloonHint')"
        >
          <a-switch
            :checked="model.balloon"
            @update:checked="(value: boolean) => update('balloon', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item
          :label="t('emulator2.avd.fieldGuestAngle')"
          :extra="t('emulator2.avd.guestAngleHint')"
        >
          <a-switch
            :checked="model.guestAngle"
            @update:checked="(value: boolean) => update('guestAngle', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item
          :label="t('emulator2.avd.fieldHeadless')"
          :extra="t('emulator2.avd.headlessHint')"
        >
          <a-switch
            :checked="model.headless"
            @update:checked="(value: boolean) => update('headless', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>
