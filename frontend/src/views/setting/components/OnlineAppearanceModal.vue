<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useOnlineAppearance, type OnlineAppearanceInstallOutcome } from '../useOnlineAppearance'
import OnlineAppearanceDetail from './OnlineAppearanceDetail.vue'
import OnlineAppearanceList from './OnlineAppearanceList.vue'

const props = defineProps<{
  open: boolean
  install: (token: string) => Promise<OnlineAppearanceInstallOutcome>
}>()

const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
}>()

const { t } = useI18n()
const store = useOnlineAppearance({ install: token => props.install(token) })
const { view, installing } = store

const handleClose = (): void => {
  if (installing.value) return
  emit('update:open', false)
}

// 关闭时等淡出动画结束再清空，否则会先闪一下空列表。
watch(
  () => props.open,
  isOpen => {
    if (isOpen) store.open()
  },
  { immediate: true }
)

onBeforeUnmount(store.reset)
</script>

<template>
  <a-modal
    :open="open"
    :width="880"
    :z-index="90"
    :style="{ top: '32px' }"
    :footer="null"
    :closable="!installing"
    :keyboard="!installing"
    :mask-closable="!installing"
    :title="t('setting.onlineAppearance.title')"
    :after-close="store.reset"
    @cancel="handleClose"
  >
    <div class="online-appearance">
      <OnlineAppearanceList v-if="view === 'list'" :store="store" />
      <OnlineAppearanceDetail v-else :store="store" />
    </div>
  </a-modal>
</template>

<style scoped>
.online-appearance {
  display: flex;
  height: min(520px, calc(100vh - 160px));
  min-height: 0;
  flex-direction: column;
}
</style>
