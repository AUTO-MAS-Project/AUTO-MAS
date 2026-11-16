<!-- MSS 只适配桌面端：在控制方式一步顶部（插入点 beforeControl）提醒，只在当前生效的控制方式
     不是桌面端时出现；interface 还没读到（控制器类型为空）时不提示 -->
<template>
  <a-alert
    v-if="showHint"
    class="flavor-controller-hint"
    type="warning"
    show-icon
    :message="t('core.edit.mssFlavorControllerHint')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaFWScriptSlotContext } from '@/composables/maafwFlavorTypes'

const { t } = useI18n()

const props = defineProps<{
  context: MaaFWScriptSlotContext
}>()

const showHint = computed(() => {
  const type = props.context.effectiveControllerType
  return Boolean(type) && type !== 'Win32'
})
</script>

<style scoped>
.flavor-controller-hint {
  margin-bottom: 16px;
}
</style>
