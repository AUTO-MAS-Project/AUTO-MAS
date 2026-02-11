/**
 * 应用初始化状态管理
 */

import { ref } from 'vue'
const logger = window.electronAPI.getLogger('应用初始化')

// 全局初始化状态 - 在所有组件间共享
const isInitialized = ref(false)


/**
 * 标记应用已初始化完成
 */
export function markAsInitialized() {
    isInitialized.value = true
    logger.info('应用已标记为初始化完成')
}

/**
 * 重置初始化状态（用于测试或重新初始化）
 */
export function resetInitializationStatus() {
    isInitialized.value = false
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
