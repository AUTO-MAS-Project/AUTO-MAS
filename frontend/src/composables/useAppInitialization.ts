/**
 * 应用初始化状态管理
 */

import { ref } from 'vue'

const logger = window.electronAPI?.getLogger?.('应用初始化') || console

// 异步从主进程读取初始化状态
async function getPersistedInitialized(): Promise<boolean> {
  try {
    return await window.electronAPI.getAppInitialized()
  } catch (e) {
    logger.warn('读取初始化状态失败，回退到未初始化', e)
    return false
  }
}

// 保存初始化状态到主进程
async function persistInitialized(value: boolean): Promise<void> {
  try {
    await window.electronAPI.setAppInitialized(value)
  } catch (e) {
    logger.warn('保存初始化状态失败', e)
  }
}

// 全局初始化状态
const isInitialized = ref<boolean>(false)

// 开发模式：直接跳过初始化，不回填
if (import.meta.env.DEV) {
  isInitialized.value = true
  logger.info('开发环境：初始化状态默认为 true')
} else {
  // 生产模式：异步回填
  getPersistedInitialized().then((value) => {
    isInitialized.value = value
  })
}


/**
 * 标记应用已初始化完成
 */
export async function markAsInitialized() {
  isInitialized.value = true
  await persistInitialized(true)
  logger.info('应用已标记为初始化完成')
}

/**
 * 重置初始化状态（用于测试或重新初始化）
 */
export async function resetInitializationStatus() {
  isInitialized.value = false
  await persistInitialized(false)
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
