<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBoundGameTarget } from '@/composables/useBoundGameTarget'

const props = withDefaults(defineProps<{ launcher?: boolean }>(), { launcher: false })
const { t } = useI18n()
const { executable, launcher: launcherPath } = useBoundGameTarget()
const path = computed(() => (props.launcher ? launcherPath.value : executable.value))
</script>

<template>
  <div class="bound-game-path">
    <a-typography-text v-if="path" code :title="String(path)">{{ path }}</a-typography-text>
    <a-typography-text v-else type="secondary">{{
      t('core.games.selectTarget')
    }}</a-typography-text>
    <router-link to="/games">{{ t('core.games.manageTargets') }}</router-link>
  </div>
</template>

<style scoped>
.bound-game-path {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-height: 40px;
}
.bound-game-path :deep(code) {
  overflow-wrap: anywhere;
}
</style>
