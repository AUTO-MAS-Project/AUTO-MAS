<!-- MSS 只适配部分控制方式：在控制方式一步顶部（插入点 beforeControl）说明原因 -->
<template>
  <a-alert
    class="flavor-controller-hint"
    type="warning"
    show-icon
    :message="t('edit.mssFlavorControllerHint')"
  />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { MaaFWScriptSlotContext } from '@/composables/maafwFlavorTypes'

const { t } = useI18n()

// 插入点组件统一以 context 一个 prop 接收上下文；这条提示用不到它
defineProps<{
  context: MaaFWScriptSlotContext
}>()
</script>

<style scoped>
.flavor-controller-hint {
  margin-bottom: 16px;
}
</style>
