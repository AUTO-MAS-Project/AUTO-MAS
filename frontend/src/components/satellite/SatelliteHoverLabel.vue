<template>
  <div v-show="name" ref="element" class="satellite-label">
    <span class="satellite-label-name">{{ name }}</span>
    <span v-if="statusText" class="satellite-label-status">{{ statusText }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import type { ScreenPoint } from './satelliteScene'

/** 悬停在卫星上时的标签：脚本名（通用 MFW 是项目名），有运行状态时带上状态 */
const props = defineProps<{
  name: string | null
  status?: SatelliteModuleStatus
}>()

const { t } = useI18n()
const element = ref<HTMLDivElement | null>(null)

const statusText = computed(() => {
  const status = props.status
  if (!status) return ''
  if (status.lastFailed) {
    return t(status.running ? 'home.satelliteStatus.failedRunning' : 'home.satelliteStatus.failed')
  }
  if (status.running) return t('home.satelliteStatus.running')
  if (status.queued) return t('home.satelliteStatus.queued')
  return ''
})

/** 标签跟着卫星走，每帧直接改样式，不经过响应式 */
function moveTo(point: ScreenPoint): void {
  if (!element.value) return
  element.value.style.transform = `translate(${point.x}px, ${point.y - 52}px) translate(-50%, -100%)`
}

defineExpose({ moveTo })
</script>

<style scoped>
.satellite-label {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-elevated);
  box-shadow: var(--ant-box-shadow-secondary);
  color: var(--ant-color-text);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  pointer-events: none;
}

.satellite-label-name {
  font-weight: 600;
}

.satellite-label-status {
  color: var(--ant-color-text-secondary);
}
</style>
