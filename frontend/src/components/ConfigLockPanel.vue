<template>
  <div :class="contentClass" :inert="configLocked">
    <ConfigProvider :component-disabled="configLocked">
      <a-alert
        v-if="configLocked"
        class="config-lock-alert"
        type="warning"
        show-icon
        :message="t('core.edit.configLocked')"
      />
      <slot :locked="configLocked" />
      <GameBindingSection v-if="showBottomGameBinding" :script-id="scriptId" />
    </ConfigProvider>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ConfigProvider } from 'ant-design-vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import GameBindingSection from '@/components/GameBindingSection.vue'

const props = withDefaults(
  defineProps<{
    scriptId: string
    userId?: string
    contentClass: string
    gameBinding?: 'auto' | 'none'
  }>(),
  { gameBinding: 'auto', userId: undefined }
)

const { t } = useI18n()
const route = useRoute()
const { configLocked } = useScriptConfigLock(() =>
  props.userId ? { scriptId: props.scriptId, userId: props.userId } : props.scriptId
)
const isAccountPage = computed(() => typeof route.params.userId === 'string')
const isExcludedSubPage = computed(
  () =>
    route.meta.scriptPage === 'userAdd' ||
    route.path.includes('/users/add/') ||
    route.path.includes('/cultivation')
)
const showBottomGameBinding = computed(
  () => props.gameBinding !== 'none' && !isExcludedSubPage.value && isAccountPage.value
)
</script>

<style scoped>
.config-lock-alert {
  margin-bottom: 16px;
}
</style>
