/**
 * 应用初始化状态管理
 */

import { ref } from 'vue'

const STORAGE_KEY = 'app-initialized'

// 从 localStorage 读取初始化状态
function getPersistedInitialized(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'true'
}

// 保存初始化状态到 localStorage
function persistInitialized(value: boolean) {
  localStorage.setItem(STORAGE_KEY, String(value))
}

// 全局初始化状态 - 从 localStorage 读取初始值
const isInitialized = ref(getPersistedInitialized())

const logger = window.electronAPI?.getLogger?.('应用初始化') || console


/**
 * 标记应用已初始化完成
 */
export function markAsInitialized() {
  isInitialized.value = true
  persistInitialized(true)
  logger.info('应用已标记为初始化完成')
}

/**
 * 重置初始化状态（用于测试或重新初始化）
 */
export function resetInitializationStatus() {
  isInitialized.value = false
  persistInitialized(false)
  logger.info('应用初始化状态已重置')
}

/**
 * 使用应用初始化状态的 composable
 */
export function useAppInitialization() {
  return {
    isInitialized,
    markAsInitialized,
    resetInitializationStatus,
  }
}
