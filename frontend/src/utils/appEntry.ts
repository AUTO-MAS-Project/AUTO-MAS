// appEntry.ts - 统一的应用进入逻辑
import router from '@/router'
import { connectAfterBackendStart, forceConnectWebSocket } from '@/composables/useWebSocket'
import { startTitlebarVersionCheck } from '@/composables/useVersionService'
import { useUpdateChecker } from '@/composables/useUpdateChecker'
import { markAsInitialized } from '@/composables/useAppInitialization'
import { useAppStartup } from '@/composables/useAppStartup'
import { bootstrapSchedulerSubscriptions } from '@/views/scheduler/schedulerHandlers'

const logger = window.electronAPI.getLogger('应用入口')

// 单飞行标记。必须在第一个 await 之前赋值，否则并发调用都会越过守卫。
let versionServicesPromise: Promise<void> | null = null

/**
 * 启动所有版本检查服务
 * 包括：
 * 1. 标题栏版本信息检查（10分钟一次）
 * 2. 版本更新检查（4小时一次，带弹窗提醒）
 */
function startVersionServices(): Promise<void> {
  if (versionServicesPromise) {
    logger.info('版本检查服务已启动，跳过重复启动')
    return versionServicesPromise
  }
  versionServicesPromise = runVersionServices()
  return versionServicesPromise
}

async function runVersionServices(): Promise<void> {
  logger.info('开始启动版本检查服务...')

  // 两个服务互不依赖，且各自的首次检查都会打网络；并行启动，单个失败不影响另一个。
  const [titlebarResult, updateCheckerResult] = await Promise.allSettled([
    startTitlebarVersionCheck(),
    useUpdateChecker().startPolling(),
  ])

  const describe = (reason: unknown): string =>
    reason instanceof Error ? reason.message : String(reason)

  if (titlebarResult.status === 'fulfilled') {
    logger.info('标题栏版本检查服务已启动（每10分钟检查一次）')
  } else {
    logger.error(`启动标题栏版本检查服务失败: ${describe(titlebarResult.reason)}`)
  }

  if (updateCheckerResult.status === 'fulfilled') {
    logger.info('版本更新检查服务已启动（每4小时检查一次）')
  } else {
    logger.error(`启动版本更新检查服务失败: ${describe(updateCheckerResult.reason)}`)
  }

  logger.info('所有版本检查服务启动完成')
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
  const { setStatus } = useAppStartup()
  setStatus('reconnecting', {
    stage: 'connection',
    message: '正在建立实时连接...',
  })
  bootstrapSchedulerSubscriptions()

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
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`${reason}：WebSocket连接尝试失败: ${errorMsg}`)
  }

  // 决定是否进入应用
  if (wsConnected || forceEnter) {
    if (!wsConnected && forceEnter) {
      logger.warn(`${reason}：WebSocket连接失败，但强制进入应用`)
    }

    setStatus('connected', {
      stage: 'ready',
      message: wsConnected ? '已准备就绪' : '已进入离线模式',
    })

    // 标记应用已初始化完成
    await markAsInitialized()

    // 预加载调度中心。连接建立时后端立即推送的快照可能早于此处的订阅建立而被丢弃，
    // useSchedulerLogic.initialize() 会在订阅就绪后补发一次 snapshot.request 拉回状态。
    preloadSchedulerView(reason)

    // 跳转到主页
    if (router.currentRoute.value.path !== '/home') {
      router.push('/home')
    }
    logger.info(`${reason}：已进入应用`)

    // 版本检查是后台定时服务，其首次检查会打网络；不要 gate 住启动遮罩的消失。
    void startVersionServices()

    // 插件市场快照预热：后台 fire-and-forget，不阻塞启动、不 gate 遮罩；
    // 失败静默，用户进入市场页时会正常重试。
    preloadPluginMarket(reason)

    return true
  } else {
    setStatus('offline', {
      stage: 'connection',
      detail: '实时连接建立失败，后端可能尚未就绪。',
    })
    logger.error(`${reason}：WebSocket连接失败且不允许强制进入`)
    return false
  }
}

/**
 * 跳过初始化（忽略WebSocket连接状态）
 * @param reason 进入原因
 */
export async function forceEnterApp(reason: string = '强行进入'): Promise<void> {
  logger.info(`${reason}：跳过初始化流程开始`)
  logger.info(`${reason}：尝试强制建立WebSocket连接...`)
  const { setStatus } = useAppStartup()
  setStatus('reconnecting', {
    stage: 'connection',
    message: '正在建立实时连接...',
  })
  bootstrapSchedulerSubscriptions()

  try {
    // 使用强制连接模式
    const wsConnected = await forceConnectWebSocket()
    if (wsConnected) {
      logger.info(`${reason}：强制WebSocket连接成功！`)
    } else {
      logger.warn(`${reason}：强制WebSocket连接失败，但继续进入应用`)
    }

    // 等待一下确保连接状态稳定
    await new Promise(resolve => setTimeout(resolve, 500))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`${reason}：强制WebSocket连接异常: ${errorMsg}`)
  }

  // 无论WebSocket是否成功，都进入应用
  logger.info(`${reason}：跳转到主页...`)

  setStatus('connected', {
    stage: 'ready',
    message: '已进入主界面',
  })

  // 标记应用已初始化完成
  await markAsInitialized()

  if (router.currentRoute.value.path !== '/home') {
    router.push('/home')
  }
  logger.info(`${reason}：已跳过初始化`)

  // 同 enterApp：后台定时服务不参与进入应用的关键路径。
  void startVersionServices()

  // 预加载调度中心
  preloadSchedulerView(reason)

  // 同 enterApp：插件市场快照后台预热，失败静默。
  preloadPluginMarket(reason)
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
 * 插件市场快照启动预热（fire-and-forget）。
 * 动态 import 避免把市场模块拉进启动关键路径；prewarmPluginMarketSnapshot
 * 内部单飞行且所有失败静默，市场页打开时无缓存会自行请求兜底。
 */
function preloadPluginMarket(reason: string): void {
  void import('../views/plugin-market/marketPrewarm')
    .then(({ prewarmPluginMarketSnapshot }) => prewarmPluginMarketSnapshot())
    .then(() => {
      logger.info(`${reason}：插件市场快照预热流程结束`)
    })
    .catch(error => {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`${reason}：插件市场快照预热失败（静默）: ${errorMsg}`)
    })
}

/**
 * 预加载调度中心
 * 静默加载调度中心逻辑
 */
async function preloadSchedulerView(reason: string) {
  logger.info(`${reason}：调度中心初始化...`)

  try {
    // 动态导入并初始化调度中心逻辑
    const { useSchedulerLogic } = await import('../views/scheduler/useSchedulerLogic')
    const { initialize } = useSchedulerLogic()

    if (initialize) {
      initialize()
      logger.info(`${reason}：调度中心就绪`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`${reason}：调度中心初始化失败: ${errorMsg}`)
  }
}
