/**
 * 版本服务 - 统一管理前端和后端版本信息获取与定时检查
 * 包含两个独立的定时器：
 * 1. 标题栏版本信息检查（10分钟一次）
 * 2. 版本更新检查（4小时一次）
 */

import { ref } from 'vue'
import { Service, type UpdateCheckOut, type VersionOut } from '@/api'
const logger = window.electronAPI.getLogger('版本服务')

// 获取版本号
const version = (import.meta as any).env.VITE_APP_VERSION || '1.0.0'

// ========== 标题栏版本信息相关 ==========
export const updateInfo = ref<UpdateCheckOut | null>(null)
export const backendUpdateInfo = ref<VersionOut | null>(null)

const TITLEBAR_POLL_MS = 10 * 60 * 1000 // 10 分钟
let titlebarPollTimer: number | null = null
const isTitlebarPolling = ref(false)

/**
 * 获取前端版本和更新信息（用于标题栏显示）
 */
const getAppVersion = async () => {
    try {
        const ver = await Service.checkUpdateApiUpdateCheckPost({
            current_version: version,
            if_force: false,
        })
        updateInfo.value = ver
        return ver
    } catch (error) {
        logger.error('获取前端版本失败:', error)
        return null
    }
}

/**
 * 获取后端版本信息（用于标题栏显示）
 */
const getBackendVersion = async () => {
    try {
        backendUpdateInfo.value = await Service.getGitVersionApiInfoVersionPost()
    } catch (error) {
        logger.error('获取后端版本失败:', error)
    }
}

/**
 * 执行一次标题栏版本信息检查
 */
const pollTitlebarVersionOnce = async () => {
    if (isTitlebarPolling.value) return
    isTitlebarPolling.value = true

    try {
        const [appRes, backendRes] = await Promise.allSettled([getAppVersion(), getBackendVersion()])

        if (appRes.status === 'rejected') {
            logger.error('获取前端版本失败:', appRes.reason)
        }
        if (backendRes.status === 'rejected') {
            logger.error('获取后端版本失败:', backendRes.reason)
        }
    } finally {
        isTitlebarPolling.value = false
    }
}

/**
 * 启动标题栏版本信息定时检查（10分钟一次）
 */
export const startTitlebarVersionCheck = async () => {
    if (titlebarPollTimer) {
        logger.warn('标题栏版本检查定时器已存在，跳过启动')
        return
    }

    logger.info('启动标题栏版本信息定时检查（每10分钟）')

    // 立即执行一次
    await pollTitlebarVersionOnce()

    // 启动定时器
    titlebarPollTimer = window.setInterval(pollTitlebarVersionOnce, TITLEBAR_POLL_MS)
}

/**
 * 停止标题栏版本信息定时检查
 */
export const stopTitlebarVersionCheck = () => {
    if (titlebarPollTimer) {
        clearInterval(titlebarPollTimer)
        titlebarPollTimer = null
        logger.info('停止标题栏版本信息定时检查')
    }
}

// ========== 版本更新检查相关（4小时）==========
// 这部分直接从 useUpdateChecker 导入，保持原有逻辑
export { useUpdateChecker, useUpdateModal } from './useUpdateChecker'
