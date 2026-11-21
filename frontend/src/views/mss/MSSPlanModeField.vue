<!-- eslint-disable vue/no-mutating-props -- Slot components edit the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <!-- MSS 的用户可以引用计划表：运行前由特调钩子按当天槽位改写任务选项 -->
  <a-form-item
    class="flavor-plan-mode"
    :label="t('core.edit.maafwFlavorPlanMode')"
    :extra="t('core.edit.mssFlavorPlanHint')"
  >
    <a-select
      v-model:value="formData.Info.PlanMode"
      :options="planModeOptions"
      :disabled="loading"
      class="flavor-plan-select"
      @change="emit('save', 'Info.PlanMode', formData.Info.PlanMode)"
    />
  </a-form-item>
  <!-- 这一轮根本跑不起来时提前说清楚，别等引擎报「没有可执行任务」 -->
  <a-alert
    v-if="queueCannotRun"
    class="flavor-queue-empty"
    type="warning"
    show-icon
    :message="t('core.edit.mssFlavorQueueEmpty')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaFWUserFormData } from '@/composables/maafwFlavorTypes'
import { buildPlanModeOptions, isMSSQueueUnrunnable, mssPlanComboxItems } from './planModeOptions'

const { t } = useI18n()

const props = defineProps<{
  formData: MaaFWUserFormData
  /** 页面仍在加载：控件置灰 */
  loading: boolean
  /** 任务队列里的任务实例数（虚影不算） */
  queuedTaskCount: number
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

const planModeOptions = computed(() =>
  buildPlanModeOptions(mssPlanComboxItems.value, t('core.edit.maafwFlavorPlanFixed'))
)

const queueCannotRun = computed(() =>
  isMSSQueueUnrunnable(props.queuedTaskCount, props.formData.Info.PlanMode)
)
</script>

<style scoped>
.flavor-plan-select {
  width: 100%;
  max-width: 360px;
}
</style>
