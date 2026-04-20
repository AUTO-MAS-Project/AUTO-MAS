/**
 * 版本服务 - 统一管理前端和后端版本信息获取与定时检查
 * 包含两个独立的定时器：
 * 1. 标题栏版本信息检查（10分钟一次）
 * 2. 版本更新检查（4小时一次）
 */

import { ref } from 'vue'
import { infoApi, updateApi, type UpdateCheckOut, type VersionOut } from '@/api'
const logger = window.electronAPI.getLogger('版本服务')

const formatError = (error: unknown): string => {
    if (error instanceof Error) {
        return error.message || error.name
    }

    if (typeof Response !== 'undefined' && error instanceof Response) {
        const statusText = error.statusText ? ` ${error.statusText}` : ''
        return `HTTP ${error.status}${statusText}`
    }

    if (typeof Event !== 'undefined' && error instanceof Event) {
        const target = (error.target as { tagName?: string } | null)?.tagName
        return target ? `Event: ${error.type} (target: ${target})` : `Event: ${error.type}`
    }

    if (error === null || error === undefined) {
        return String(error)
    }

    if (typeof error === 'string') {
        return error
    }

    if (typeof error === 'object') {
        const maybeMessage = (error as Record<string, unknown>).message
        if (typeof maybeMessage === 'string' && maybeMessage.trim()) {
            return maybeMessage
        }

        try {
            return JSON.stringify(error)
        } catch {
            return Object.prototype.toString.call(error)
        }
    }

    return String(error)
}

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
        const ver = await updateApi.check({
            current_version: version,
            if_force: false,
        })
        updateInfo.value = ver
        return ver
    } catch (error) {
        const errorMsg = formatError(error)
        logger.error(`获取前端版本失败: ${errorMsg}`)
        return null
    }
}

/**
 * 获取后端版本信息（用于标题栏显示）
 */
export const getBackendVersion = async () => {
    try {
        backendUpdateInfo.value = await infoApi.getVersion()
    } catch (error) {
        const errorMsg = formatError(error)
        logger.error(`获取后端版本失败: ${errorMsg}`)
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
            const errorMsg = formatError(appRes.reason)
            logger.error(`获取前端版本失败: ${errorMsg}`)
        }
        if (backendRes.status === 'rejected') {
            const errorMsg = formatError(backendRes.reason)
            logger.error(`获取后端版本失败: ${errorMsg}`)
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

// ========== 版本更新检查相关（4小时） ==========
// 这部分直接从 useUpdateChecker 导入，保持原有逻辑
export { useUpdateChecker, useUpdateModal } from './useUpdateChecker'

