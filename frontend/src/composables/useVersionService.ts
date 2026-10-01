/**
 * 版本服务 - 统一管理前端和后端版本信息获取与定时检查
 * 包含两个独立的定时器：
 * 1. 标题栏版本信息检查（10分钟一次）
 * 2. 版本更新检查（4小时一次）
 */

import { ref } from 'vue'
import { Service, type UpdateCheckOut, type VersionOut } from '@/api'
import { readUpdatePauseState, requestUpdateCheck } from './useUpdateChecker'
const logger = window.electronAPI.getLogger('版本服务')

// ========== 标题栏版本信息相关 ==========
export const updateInfo = ref<UpdateCheckOut | null>(null)
export const backendUpdateInfo = ref<VersionOut | null>(null)
export const runtimeBackendUpdateAvailable = ref(false)
export const runtimeBackendUpdateCommitMessage = ref('')

const TITLEBAR_POLL_MS = 10 * 60 * 1000 // 10 分钟
let titlebarPollTimer: number | null = null
const isTitlebarPolling = ref(false)

/**
 * 获取前端版本和更新信息（用于标题栏显示）
 */
const getAppVersion = async () => {
  try {
    const ver = await requestUpdateCheck(false)
    updateInfo.value = ver
    return ver
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`获取前端版本失败: ${errorMsg}`)
    return null
  }
}

/**
 * 获取后端版本信息（用于标题栏显示）
 */
export const getBackendVersion = async () => {
  try {
    backendUpdateInfo.value = await Service.getGitVersionApiInfoVersionPost()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`获取后端版本失败: ${errorMsg}`)
  }
}

export const checkRuntimeBackendUpdate = async () => {
  try {
    const result = await window.electronAPI.checkRuntimeBackendUpdate?.()
    if (result?.staged === true) {
      runtimeBackendUpdateAvailable.value = true
      runtimeBackendUpdateCommitMessage.value = result.commitMessage ?? ''
    } else if (result && !result.error) {
      runtimeBackendUpdateAvailable.value = false
      runtimeBackendUpdateCommitMessage.value = ''
    }
    return result
  } catch (error) {
    logger.debug(
      `Runtime 后端更新检查失败: ${error instanceof Error ? error.message : String(error)}`
    )
    return null
  }
}

/**
 * 执行一次标题栏版本信息检查
 */
const pollTitlebarVersionOnce = async () => {
  if (isTitlebarPolling.value) return
  isTitlebarPolling.value = true

  try {
    // 暂停更新期间不发起任何更新检查，并清掉暂停前的旧提示
    // （本体"检测到更新"与后端"检测到后端更新"随之消失，到期后下个 tick 自动恢复）
    // 读取失败视为状态未知：同样跳过检查但不动现有提示（失败关闭，下个 tick 重试）
    const pauseState = await readUpdatePauseState()
    if (pauseState !== false) {
      if (pauseState === true) {
        updateInfo.value = null
        backendUpdateInfo.value = null
        runtimeBackendUpdateAvailable.value = false
        runtimeBackendUpdateCommitMessage.value = ''
      }
      return
    }

    const [appRes, backendRes, runtimeRes] = await Promise.allSettled([
      getAppVersion(),
      getBackendVersion(),
      checkRuntimeBackendUpdate(),
    ])

    if (appRes.status === 'rejected') {
      const errorMsg =
        appRes.reason instanceof Error ? appRes.reason.message : String(appRes.reason)
      logger.error(`获取前端版本失败: ${errorMsg}`)
    }
    if (backendRes.status === 'rejected') {
      const errorMsg =
        backendRes.reason instanceof Error ? backendRes.reason.message : String(backendRes.reason)
      logger.error(`获取后端版本失败: ${errorMsg}`)
    }
    if (runtimeRes.status === 'rejected') {
      logger.debug(`Runtime 后端更新检查失败: ${String(runtimeRes.reason)}`)
    }
  } finally {
    isTitlebarPolling.value = false
  }
}

/**
 * 启动标题栏版本信息定时检查（10分钟一次）
 * 暂停更新期间定时器照常待命（每次 tick 由 getAppVersion 门控跳过），到期后自动恢复
 */
export const startTitlebarVersionCheck = async () => {
  if (titlebarPollTimer) {
    logger.warn('标题栏版本检查定时器已存在，跳过启动')
    return
  }

  if ((await readUpdatePauseState()) === true) {
    logger.info('更新已暂停，标题栏版本信息检查待命（暂停期内不检查，到期后自动恢复）')
  } else {
    logger.info('启动标题栏版本信息定时检查（每10分钟）')
  }

  // 首次检查在后台执行，不阻塞应用进入主页
  void pollTitlebarVersionOnce()

  // 启动定时器
  titlebarPollTimer = window.setInterval(pollTitlebarVersionOnce, TITLEBAR_POLL_MS)
}

// ========== 版本更新检查相关（4小时）==========
// 这部分直接从 useUpdateChecker 导入，保持原有逻辑
export { useUpdateChecker, useUpdateModal } from './useUpdateChecker'
