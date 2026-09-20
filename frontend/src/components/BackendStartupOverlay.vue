<template>
  <Teleport to="body">
    <div v-if="visible" class="backend-startup-overlay">
      <div class="startup-card">
        <LaunchStatus
          :title="t('launch.starting')"
          :hint="slow ? t('launch.slowHint') : ''"
          :action-label="slow ? t('launch.viewLog') : ''"
          @action="openLaunchLogWindow('后端启动遮罩')"
        />
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import LaunchStatus from './LaunchStatus.vue'
import { SLOW_LAUNCH_THRESHOLD_MS, openLaunchLogWindow } from '@/utils/launch'

defineOptions({ name: 'BackendStartupOverlay' })

const props = defineProps<{
  visible: boolean
}>()

const { t } = useI18n()

const slow = ref(false)
let slowTimer: ReturnType<typeof setTimeout> | null = null

function clearSlowTimer() {
  if (!slowTimer) return
  clearTimeout(slowTimer)
  slowTimer = null
}

// 正常启动到不了这个阈值，超过了才提示，并给一个能点开日志的出口。
watch(
  () => props.visible,
  isVisible => {
    clearSlowTimer()
    slow.value = false
    if (!isVisible) return
    slowTimer = setTimeout(() => {
      slow.value = true
    }, SLOW_LAUNCH_THRESHOLD_MS)
  },
  { immediate: true }
)

onUnmounted(clearSlowTimer)
</script>

<style scoped>
.backend-startup-overlay {
  position: fixed;
  top: 32px;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 9998;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-bg-mask, rgba(0, 0, 0, 0.45));
  backdrop-filter: blur(4px);
  animation: overlay-fade-in 0.2s ease-out;
}

.startup-card {
  padding: 30px 34px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  background: var(--ant-color-bg-elevated);
  box-shadow: 0 10px 36px rgba(0, 0, 0, 0.24);
}

@keyframes overlay-fade-in {
  from {
    opacity: 0;
    transform: scale(0.98);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .backend-startup-overlay {
    animation: none;
  }
}
</style>
