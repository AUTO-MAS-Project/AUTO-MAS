<!-- eslint-disable vue/no-mutating-props -- Slot components edit the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <!-- 队列里没有活动任务时，活动期间要不要自动加进来（字段名仍叫 IfActivityFirst；已在队列里的
       活动任务不看这个开关）。后端缺省是开，所以这里按「不是 false 就算开」显示，
       不必给 MaaFW 用户塞一个它没有的字段 -->
  <a-form-item
    class="flavor-activity-first"
    :label="t('core.edit.mssFlavorActivityFirst')"
    :extra="t('core.edit.mssFlavorActivityFirstHint')"
  >
    <a-switch
      :checked="formData.Info.IfActivityFirst !== false"
      :disabled="loading"
      @change="handleActivityFirstChange"
    />
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { MaaFWUserFormData } from '@/composables/maafwFlavorTypes'

const { t } = useI18n()

const props = defineProps<{
  formData: MaaFWUserFormData
  /** 页面仍在加载：控件置灰 */
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

/** 后端缺省是开，这里只在用户显式关掉时写 false */
const handleActivityFirstChange = (checked: boolean | string | number) => {
  props.formData.Info.IfActivityFirst = checked === true
  emit('save', 'Info.IfActivityFirst', props.formData.Info.IfActivityFirst)
}
</script>
