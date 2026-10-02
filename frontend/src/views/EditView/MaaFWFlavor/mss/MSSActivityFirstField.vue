<!-- eslint-disable vue/no-mutating-props -- Slot components edit the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <!-- 活动优先是 MSS 自己的取舍。后端缺省是开，所以这里按「不是 false 就算开」显示，
       不必给 MaaFW 用户塞一个它没有的字段 -->
  <a-form-item
    class="flavor-activity-first"
    :label="t('edit.mssFlavorActivityFirst')"
    :extra="t('edit.mssFlavorActivityFirstHint')"
  >
    <a-switch
      :checked="context.formData.Info.IfActivityFirst !== false"
      :disabled="context.loading"
      @change="handleActivityFirstChange"
    />
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { MaaFWUserSlotContext } from '@/composables/maafwFlavorTypes'

const { t } = useI18n()

const props = defineProps<{
  context: MaaFWUserSlotContext
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

/** 后端缺省是开，这里只在用户显式关掉时写 false */
const handleActivityFirstChange = (checked: boolean | string | number) => {
  props.context.formData.Info.IfActivityFirst = checked === true
  emit('save', 'Info.IfActivityFirst', props.context.formData.Info.IfActivityFirst)
}
</script>
