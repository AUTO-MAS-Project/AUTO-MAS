<template>
  <div :class="contentClass" :inert="configLocked">
    <ConfigProvider :component-disabled="configLocked">
      <a-alert
        v-if="configLocked"
        class="config-lock-alert"
        type="warning"
        show-icon
        :message="t('edit.configLocked')"
      />
      <slot />
    </ConfigProvider>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ConfigProvider } from 'ant-design-vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'

const props = defineProps<{
  scriptId: string
  contentClass: string
}>()

const { t } = useI18n()
const { configLocked } = useScriptConfigLock(() => props.scriptId)
</script>

<style scoped>
.config-lock-alert {
  margin-bottom: 16px;
}
</style>
