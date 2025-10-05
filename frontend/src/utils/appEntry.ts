// appEntry.ts - 统一的应用进入逻辑
import router from '@/router'
import { connectAfterBackendStart, forceConnectWebSocket } from '@/composables/useWebSocket'

/**
 * 统一的进入应用函数，会自动尝试建立WebSocket连接
 * @param reason 进入应用的原因，用于日志记录
 * @param forceEnter 是否强制进入（即使WebSocket连接失败）
 * @returns Promise<boolean> 是否成功进入应用
 */
export async function enterApp(
  reason: string = '正常进入',
  forceEnter: boolean = true
): Promise<boolean> {
  console.log(`${reason}：开始进入应用流程，尝试建立WebSocket连接...`)

  let wsConnected = false

  try {
    // 尝试建立WebSocket连接
    wsConnected = await connectAfterBackendStart()
    if (wsConnected) {
      console.log(`${reason}：WebSocket连接建立成功`)
    } else {
      console.warn(`${reason}：WebSocket连接建立失败`)
    }
  } catch (error) {
    console.error(`${reason}：WebSocket连接尝试失败:`, error)
  }

  // 决定是否进入应用
  if (wsConnected || forceEnter) {
    if (!wsConnected && forceEnter) {
      console.warn(`${reason}：WebSocket连接失败，但强制进入应用`)
    }

    // 跳转到主页
    router.push('/home')
    console.log(`${reason}：已进入应用`)
    return true
  } else {
    console.error(`${reason}：WebSocket连接失败且不允许强制进入`)
    return false
  }
}

/**
 * 强行进入应用（忽略WebSocket连接状态）
 * @param reason 进入原因
 */
export async function forceEnterApp(reason: string = '强行进入'): Promise<void> {
  console.log(`🚀 ${reason}：强行进入应用流程开始`)
  console.log(`📡 ${reason}：尝试强制建立WebSocket连接...`)

  try {
    // 使用强制连接模式
    const wsConnected = await forceConnectWebSocket()
    if (wsConnected) {
      console.log(`✅ ${reason}：强制WebSocket连接成功！`)
    } else {
      console.warn(`⚠️  ${reason}：强制WebSocket连接失败，但继续进入应用`)
    }

    // 等待一下确保连接状态稳定
    await new Promise(resolve => setTimeout(resolve, 500))
  } catch (error) {
    console.error(`❌ ${reason}：强制WebSocket连接异常:`, error)
  }

  // 无论WebSocket是否成功，都进入应用
  console.log(`🏠 ${reason}：跳转到主页...`)
  router.push('/home')
  console.log(`✨ ${reason}：已强行进入应用`)
}

/**
 * 正常进入应用（需要WebSocket连接成功）
 * @param reason 进入原因
 * @returns 是否成功进入
 */
export async function normalEnterApp(reason: string = '正常进入'): Promise<boolean> {
  return await enterApp(reason, false)
}
