<!-- MSS 只适配桌面端：在 MSS 专属脚本页控制方式一步顶部提醒，只在当前生效的控制方式
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

const { t } = useI18n()

const props = defineProps<{
  /** 当前生效的控制器类型（Adb / Win32 …）；interface 没读到时为空串 */
  controllerType: string
}>()

const showHint = computed(() => {
  const type = props.controllerType
  return Boolean(type) && type !== 'Win32'
})
</script>

<style scoped>
.flavor-controller-hint {
  margin-bottom: 16px;
}
</style>
