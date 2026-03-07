import { computed, ref } from 'vue'

const logger = window.electronAPI.getLogger('应用初始化')

const isInitialized = ref(false)
const isBootstrapping = ref(false)
const isAppReady = computed(() => isInitialized.value || isBootstrapping.value)

export function markAsInitialized() {
  isInitialized.value = true
  isBootstrapping.value = false
  logger.info('应用已标记为初始化完成')
}

export function beginBootstrap() {
  isBootstrapping.value = true
  logger.info('应用启动过渡状态已开启')
}

export function finishBootstrap() {
  isBootstrapping.value = false
  logger.info('应用启动过渡状态已结束')
}

export function resetInitializationStatus() {
  isInitialized.value = false
  isBootstrapping.value = false
  logger.info('应用初始化状态已重置')
}

export function useAppInitialization() {
  return {
    isInitialized,
    isBootstrapping,
    isAppReady,
    markAsInitialized,
    beginBootstrap,
    finishBootstrap,
    resetInitializationStatus,
  }
}
