// appEntry.ts - 统一的应用进入逻辑
import router from '@/router'
import { connectAfterBackendStart, forceConnectWebSocket } from '@/composables/useWebSocket'
import { startTitlebarVersionCheck } from '@/composables/useVersionService'
import { useUpdateChecker } from '@/composables/useUpdateChecker'
import { markAsInitialized } from '@/composables/useAppInitialization'
import { getLogger } from '@/utils/logger'

const logger = getLogger('应用入口')

// 标记版本服务是否已启动，避免重复启动
let versionServicesStarted = false

/**
 * 启动所有版本检查服务
 * 包括：
 * 1. 标题栏版本信息检查（10分钟一次）
 * 2. 版本更新检查（4小时一次，带弹窗提醒）
 */
async function startVersionServices() {
  if (versionServicesStarted) {
    logger.info('版本检查服务已启动，跳过重复启动')
    return
  }

  try {
    logger.info('开始启动版本检查服务...')

    // 1. 启动标题栏版本信息定时检查（10分钟一次）
    await startTitlebarVersionCheck()
    logger.info('标题栏版本检查服务已启动（每10分钟检查一次）')

    // 2. 启动版本更新检查（4小时一次）
    const { startPolling } = useUpdateChecker()
    await startPolling()
    logger.info('版本更新检查服务已启动（每4小时检查一次）')

    versionServicesStarted = true
    logger.info('🎉 所有版本检查服务启动完成')
  } catch (error) {
    logger.error('启动版本检查服务失败:', error)
  }
}

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
  logger.info(`${reason}：开始进入应用流程，尝试建立WebSocket连接...`)

  let wsConnected = false

  try {
    // 尝试建立WebSocket连接
    wsConnected = await connectAfterBackendStart()
    if (wsConnected) {
      logger.info(`${reason}：WebSocket连接建立成功`)
    } else {
      logger.warn(`${reason}：WebSocket连接建立失败`)
    }
  } catch (error) {
    logger.error(`${reason}：WebSocket连接尝试失败:`, error)
  }

  // 决定是否进入应用
  if (wsConnected || forceEnter) {
    if (!wsConnected && forceEnter) {
      logger.warn(`${reason}：WebSocket连接失败，但强制进入应用`)
    }

    // 标记应用已初始化完成，触发其他组件挂载
    markAsInitialized()

    // 预加载调度中心
    preloadSchedulerView(reason)

    // 跳转到主页
    router.push('/home')
    logger.info(`${reason}：已进入应用`)

    // 启动版本检查服务
    await startVersionServices()

    return true
  } else {
    logger.error(`${reason}：WebSocket连接失败且不允许强制进入`)
    return false
  }
}

/**
 * 跳过初始化（忽略WebSocket连接状态）
 * @param reason 进入原因
 */
export async function forceEnterApp(reason: string = '强行进入'): Promise<void> {
  logger.info(`🚀 ${reason}：跳过初始化流程开始`)
  logger.info(`📡 ${reason}：尝试强制建立WebSocket连接...`)

  try {
    // 使用强制连接模式
    const wsConnected = await forceConnectWebSocket()
    if (wsConnected) {
      logger.info(`${reason}：强制WebSocket连接成功！`)
    } else {
      logger.warn(`⚠️  ${reason}：强制WebSocket连接失败，但继续进入应用`)
    }

    // 等待一下确保连接状态稳定
    await new Promise(resolve => setTimeout(resolve, 500))
  } catch (error) {
    logger.error(`❌ ${reason}：强制WebSocket连接异常:`, error)
  }

  // 无论WebSocket是否成功，都进入应用
  logger.info(`🏠 ${reason}：跳转到主页...`)

  // 标记应用已初始化完成，触发其他组件挂载
  markAsInitialized()

  router.push('/home')
  logger.info(`✨ ${reason}：已跳过初始化`)

  // 启动版本检查服务
  await startVersionServices()

  // 预加载调度中心
  preloadSchedulerView(reason)
}

/**
 * 正常进入应用（需要WebSocket连接成功）
 * @param reason 进入原因
 * @returns 是否成功进入
 */
export async function normalEnterApp(reason: string = '正常进入'): Promise<boolean> {
  return await enterApp(reason, false)
}

/**
 * 预加载调度中心
 * 静默加载调度中心逻辑
 */
async function preloadSchedulerView(reason: string) {
  logger.info(`调度中心初始化...`)

  try {
    // 动态导入并初始化调度中心逻辑
    const { useSchedulerLogic } = await import('../views/scheduler/useSchedulerLogic')
    const { initialize } = useSchedulerLogic()

    if (initialize) {
      initialize()
      logger.info(`调度中心就绪`)
    }
  } catch (error) {
    logger.error(`调度中心初始化失败:`, error)
  }
}
