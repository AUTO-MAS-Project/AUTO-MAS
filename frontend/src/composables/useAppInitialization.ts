/**
 * 应用初始化状态管理
 */

import { ref } from 'vue'

const logger = window.electronAPI?.getLogger?.('应用初始化') || console

// 获取前端版本号
const getAppVersion = () => (import.meta as any).env.VITE_APP_VERSION || '1.0.0'

// 异步从主进程读取初始化版本号
async function getPersistedInitializedVersion(): Promise<string | null> {
  try {
    return await window.electronAPI.getInitializedVersion()
  } catch (e) {
    logger.warn('读取初始化版本失败，回退到未初始化', e)
    return null
  }
}

// 保存初始化版本号到主进程
async function persistInitializedVersion(version: string): Promise<void> {
  try {
    await window.electronAPI.setInitializedVersion(version)
  } catch (e) {
    logger.warn('保存初始化版本失败', e)
  }
}

// 全局初始化状态（版本号字符串，null 表示未初始化）
const initializedVersion = ref<string | null>(null)

// 开发模式：直接跳过初始化，不回填
if (import.meta.env.DEV) {
  initializedVersion.value = getAppVersion()
  logger.info('开发环境：初始化状态默认为已初始化')
} else {
  // 生产模式：异步回填
  getPersistedInitializedVersion().then((version) => {
    initializedVersion.value = version
  })
}

/**
 * 标记应用已初始化完成
 */
export async function markAsInitialized() {
  const version = getAppVersion()
  initializedVersion.value = version
  await persistInitializedVersion(version)
  logger.info(`应用已标记为初始化完成，版本: ${version}`)
}

/**
 * 重置初始化状态（用于测试或重新初始化）
 */
export async function resetInitializationStatus() {
  initializedVersion.value = null
  await persistInitializedVersion('')
  logger.info('应用初始化状态已重置')
}

/**
 * 使用应用初始化状态的 composable
 */
export function useAppInitialization() {
  return {
    isInitialized: initializedVersion,
    markAsInitialized,
    resetInitializationStatus,
  }
}
