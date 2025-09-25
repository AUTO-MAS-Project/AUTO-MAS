// schedulerHandlers.ts
// 提供在调度中心 UI 未加载前也能工作的消息处理实现。
// 核心策略：将重要事件保存到 localStorage（或内存队列），并暴露注册点供 UI 在挂载时接收并回放。

// no types needed here to avoid circular/unused imports

const PENDING_TABS_KEY = 'scheduler-pending-tabs'
const PENDING_COUNTDOWN_KEY = 'scheduler-pending-countdown'
const POWER_ACTION_KEY = 'scheduler-power-action'

type UIHooks = {
    onNewTab?: (tab: any) => void
    onCountdown?: (data: any) => void
}

let uiHooks: UIHooks = {}

export function registerSchedulerUI(hooks: UIHooks) {
    uiHooks = { ...uiHooks, ...hooks }
}

// helper: push pending tab id to localStorage
function pushPendingTab(taskId: string) {
    try {
        const raw = localStorage.getItem(PENDING_TABS_KEY)
        const arr = raw ? JSON.parse(raw) : []
        if (!arr.includes(taskId)) {
            arr.push(taskId)
            localStorage.setItem(PENDING_TABS_KEY, JSON.stringify(arr))
        }
    } catch (e) {
        // ignore
    }
}

function popPendingTabs(): string[] {
    try {
        const raw = localStorage.getItem(PENDING_TABS_KEY)
        if (!raw) return []
        localStorage.removeItem(PENDING_TABS_KEY)
        return JSON.parse(raw)
    } catch (e) {
        return []
    }
}

function storePendingCountdown(data: any) {
    try {
        localStorage.setItem(PENDING_COUNTDOWN_KEY, JSON.stringify(data))
    } catch (e) {
        // ignore
    }
}

function consumePendingCountdownAndClear(): any | null {
    try {
        const raw = localStorage.getItem(PENDING_COUNTDOWN_KEY)
        if (!raw) return null
        localStorage.removeItem(PENDING_COUNTDOWN_KEY)
        return JSON.parse(raw)
    } catch (e) {
        return null
    }
}

function savePowerAction(value: string) {
    try {
        localStorage.setItem(POWER_ACTION_KEY, value)
    } catch (e) {
        // ignore
    }
}

// 导出：供 useWebSocket 在模块加载时就能使用的处理函数
export function handleTaskManagerMessage(wsMessage: any) {
    if (!wsMessage || typeof wsMessage !== 'object') return
    const { type, data } = wsMessage
    try {
        if (type === 'Signal' && data && data.newTask) {
            const taskId = String(data.newTask)
            // 将任务 ID 写入 pending 队列，UI 在挂载时会回放
            pushPendingTab(taskId)

            // 如果 UI 已注册回调，则立即通知
            if (uiHooks.onNewTab) {
                try {
                    uiHooks.onNewTab({ title: `调度台自动-${taskId}`, websocketId: taskId })
                } catch (e) {
                    console.warn('[SchedulerHandlers] onNewTab handler error:', e)
                }
            }
        }
    } catch (e) {
        console.warn('[SchedulerHandlers] handleTaskManagerMessage error:', e)
    }
}

export function handleMainMessage(wsMessage: any) {
    if (!wsMessage || typeof wsMessage !== 'object') return
    const { type, data } = wsMessage
    try {
        if (type === 'Signal' && data && data.RequestClose) {
            // 处理后端请求前端关闭的信号
            console.log('收到后端关闭请求，开始执行应用自杀...')
            handleRequestClose()
        } else if (type === 'Message' && data && data.type === 'Countdown') {
            // 存储倒计时消息，供 UI 回放
            storePendingCountdown(data)
            if (uiHooks.onCountdown) {
                try {
                    uiHooks.onCountdown(data)
                } catch (e) {
                    console.warn('[SchedulerHandlers] onCountdown handler error:', e)
                }
            }
        } else if (type === 'Update' && data && data.PowerSign !== undefined) {
            // 保存电源操作显示值（供 UI 加载时读取）
            savePowerAction(String(data.PowerSign))
        }
    } catch (e) {
        console.warn('[SchedulerHandlers] handleMainMessage error:', e)
    }
}

// 处理后端请求关闭的函数
async function handleRequestClose() {
    try {
        console.log('开始执行前端自杀流程...')
        
        // 使用更激进的强制退出方法
        if (window.electronAPI?.forceExit) {
            console.log('执行强制退出...')
            await window.electronAPI.forceExit()
        } else if (window.electronAPI?.windowClose) {
            // 备用方法：先尝试正常关闭
            console.log('执行窗口关闭...')
            await window.electronAPI.windowClose()
            setTimeout(async () => {
                if (window.electronAPI?.appQuit) {
                    await window.electronAPI.appQuit()
                }
            }, 500)
        } else {
            // 最后的备用方法
            console.log('使用页面重载作为最后手段...')
            window.location.reload()
        }
    } catch (error) {
        console.error('执行自杀流程失败:', error)
        // 如果所有方法都失败，尝试页面重载
        try {
            window.location.reload()
        } catch (e) {
            console.error('页面重载也失败:', e)
        }
    }
}

// UI 在挂载时调用，消费并回放 pending 数据
export function consumePendingTabIds(): string[] {
    return popPendingTabs()
}

export function consumePendingCountdown(): any | null {
    return consumePendingCountdownAndClear()
}

export default {
    handleTaskManagerMessage,
    handleMainMessage,
    registerSchedulerUI,
    consumePendingTabIds,
    consumePendingCountdown,
}
