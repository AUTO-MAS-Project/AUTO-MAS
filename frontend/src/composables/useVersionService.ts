/**
 * 鐗堟湰鏈嶅姟 - 缁熶竴绠＄悊鍓嶇鍜屽悗绔増鏈俊鎭幏鍙栦笌瀹氭椂妫€鏌?
 * 鍖呭惈涓や釜鐙珛鐨勫畾鏃跺櫒锛?
 * 1. 鏍囬鏍忕増鏈俊鎭鏌ワ紙10鍒嗛挓涓€娆★級
 * 2. 鐗堟湰鏇存柊妫€鏌ワ紙4灏忔椂涓€娆★級
 */

import { ref } from 'vue'
import { infoApi, updateApi, type UpdateCheckOut, type VersionOut } from '@/api'
const logger = window.electronAPI.getLogger('鐗堟湰鏈嶅姟')

// 鑾峰彇鐗堟湰鍙?
const version = (import.meta as any).env.VITE_APP_VERSION || '1.0.0'

// ========== 鏍囬鏍忕増鏈俊鎭浉鍏?==========
export const updateInfo = ref<UpdateCheckOut | null>(null)
export const backendUpdateInfo = ref<VersionOut | null>(null)

const TITLEBAR_POLL_MS = 10 * 60 * 1000 // 10 鍒嗛挓
let titlebarPollTimer: number | null = null
const isTitlebarPolling = ref(false)

/**
 * 鑾峰彇鍓嶇鐗堟湰鍜屾洿鏂颁俊鎭紙鐢ㄤ簬鏍囬鏍忔樉绀猴級
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
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`鑾峰彇鍓嶇鐗堟湰澶辫触: ${errorMsg}`)
        return null
    }
}

/**
 * 鑾峰彇鍚庣鐗堟湰淇℃伅锛堢敤浜庢爣棰樻爮鏄剧ず锛?
 */
export const getBackendVersion = async () => {
    try {
        backendUpdateInfo.value = await infoApi.getVersion()
    } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`鑾峰彇鍚庣鐗堟湰澶辫触: ${errorMsg}`)
    }
}

/**
 * 鎵ц涓€娆℃爣棰樻爮鐗堟湰淇℃伅妫€鏌?
 */
const pollTitlebarVersionOnce = async () => {
    if (isTitlebarPolling.value) return
    isTitlebarPolling.value = true

    try {
        const [appRes, backendRes] = await Promise.allSettled([getAppVersion(), getBackendVersion()])

        if (appRes.status === 'rejected') {
            const errorMsg = appRes.reason instanceof Error ? appRes.reason.message : String(appRes.reason)
            logger.error(`鑾峰彇鍓嶇鐗堟湰澶辫触: ${errorMsg}`)
        }
        if (backendRes.status === 'rejected') {
            const errorMsg = backendRes.reason instanceof Error ? backendRes.reason.message : String(backendRes.reason)
            logger.error(`鑾峰彇鍚庣鐗堟湰澶辫触: ${errorMsg}`)
        }
    } finally {
        isTitlebarPolling.value = false
    }
}

/**
 * 鍚姩鏍囬鏍忕増鏈俊鎭畾鏃舵鏌ワ紙10鍒嗛挓涓€娆★級
 */
export const startTitlebarVersionCheck = async () => {
    if (titlebarPollTimer) {
        logger.warn('鏍囬鏍忕増鏈鏌ュ畾鏃跺櫒宸插瓨鍦紝璺宠繃鍚姩')
        return
    }

    logger.info('鍚姩鏍囬鏍忕増鏈俊鎭畾鏃舵鏌ワ紙姣?0鍒嗛挓锛?)

    // 绔嬪嵆鎵ц涓€娆?
    await pollTitlebarVersionOnce()

    // 鍚姩瀹氭椂鍣?
    titlebarPollTimer = window.setInterval(pollTitlebarVersionOnce, TITLEBAR_POLL_MS)
}

/**
 * 鍋滄鏍囬鏍忕増鏈俊鎭畾鏃舵鏌?
 */
export const stopTitlebarVersionCheck = () => {
    if (titlebarPollTimer) {
        clearInterval(titlebarPollTimer)
        titlebarPollTimer = null
        logger.info('鍋滄鏍囬鏍忕増鏈俊鎭畾鏃舵鏌?)
    }
}

// ========== 鐗堟湰鏇存柊妫€鏌ョ浉鍏筹紙4灏忔椂锛?=========
// 杩欓儴鍒嗙洿鎺ヤ粠 useUpdateChecker 瀵煎叆锛屼繚鎸佸師鏈夐€昏緫
export { useUpdateChecker, useUpdateModal } from './useUpdateChecker'

