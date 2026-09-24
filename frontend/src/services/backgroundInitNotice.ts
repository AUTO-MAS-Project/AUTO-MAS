// 后端后台初始化结果提示
// 后端 lifespan 先让核心 API 就绪，再在后台挂 MCP、清理历史、起主定时器等；任一步失败
// 只体现在 /api/core/health 的 backgroundStatus / backgroundError / backgroundWarnings 里。
// 主连接建立（含重连）
// 后查一次：初始化还没跑完就按固定间隔等到终态，超过上限不再等，不做常驻轮询。

import { h } from 'vue'
import { notification } from 'ant-design-vue'
import { Service, type BackendHealthOut } from '@/api'
import { translate as t } from '@/i18n'

const logger = window.electronAPI.getLogger('后台初始化')

// 后台初始化通常几秒内结束，最慢的活动关卡请求也在一分钟内；超过上限说明卡住了，
// 不再追着问，下次连接时再查
const POLL_INTERVAL = 2000
const MAX_ATTEMPTS = 30
const NOTICE_KEY = 'backend-background-init'

export type BackgroundInitOutcome =
  | { kind: 'pending' }
  | { kind: 'ok' }
  // 主定时器已启动，只有可选步骤失败
  | { kind: 'degraded'; detail: string }
  // 主定时器没有启动，或初始化整体中断
  | { kind: 'failed'; detail: string }
  | { kind: 'ignored' }

const joinItems = (items: Array<string | null | undefined>): string =>
  items
    .map(item => item?.trim() ?? '')
    .filter(Boolean)
    .join('；')

/**
 * 把 health 响应归类成前端要不要提示、提示什么。
 *
 * backgroundStatus 取值与 AUTO-MAS-Runtime 共用（starting / running / ready / failed /
 * cancelled）。可选步骤的失败只放在 backgroundWarnings 里、状态仍是 ready——Runtime 把
 * backgroundError 非空判为启动失败，所以降级不能走 backgroundError。
 */
export function resolveBackgroundInit(
  health: Pick<BackendHealthOut, 'backgroundStatus' | 'backgroundError' | 'backgroundWarnings'>
): BackgroundInitOutcome {
  const warnings = health.backgroundWarnings ?? []
  switch (health.backgroundStatus) {
    case 'starting':
    case 'running':
      return { kind: 'pending' }
    case 'ready': {
      const detail = joinItems(warnings)
      return detail ? { kind: 'degraded', detail } : { kind: 'ok' }
    }
    case 'failed':
      return { kind: 'failed', detail: joinItems([health.backgroundError, ...warnings]) }
    default:
      // cancelled 只出现在后端关闭途中；未知取值不猜
      return { kind: 'ignored' }
  }
}

let generation = 0
// 同一份失败内容只提示一次：重连到同一个后端时不重复弹，用户关掉就不再打扰
let lastShownSignature: string | null = null

const delay = (ms: number): Promise<void> => new Promise(resolve => window.setTimeout(resolve, ms))

const showOutcome = (outcome: BackgroundInitOutcome): void => {
  if (outcome.kind === 'ok') {
    lastShownSignature = null
    notification.close(NOTICE_KEY)
    return
  }
  if (outcome.kind !== 'degraded' && outcome.kind !== 'failed') return

  const signature = `${outcome.kind}:${outcome.detail}`
  if (signature === lastShownSignature) return
  lastShownSignature = signature

  const failed = outcome.kind === 'failed'
  logger.error(`后端后台初始化${failed ? '失败' : '部分失败'}: ${outcome.detail || '无详情'}`)
  const lines = [
    t(failed ? 'misc.backgroundInitTimerNotStarted' : 'misc.backgroundInitTimerStarted'),
  ]
  if (outcome.detail) lines.push(t('misc.backgroundInitFailedSteps', { steps: outcome.detail }))
  const args = {
    key: NOTICE_KEY,
    message: t(failed ? 'misc.backgroundInitFailedTitle' : 'misc.backgroundInitDegradedTitle'),
    description: () =>
      h(
        'div',
        { style: { whiteSpace: 'pre-wrap' } },
        lines.map((line, index) => h('div', { key: index }, line))
      ),
    // 保留到用户手动关闭
    duration: null,
  }
  if (failed) {
    notification.error(args)
  } else {
    notification.warning(args)
  }
}

/**
 * 查询一次后端后台初始化结果，失败或降级时给出可关闭的通知。
 * 重复调用时只保留最新一次，旧的等待自行作废。
 */
export async function checkBackgroundInit(): Promise<void> {
  const current = ++generation
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    if (attempt > 0) await delay(POLL_INTERVAL)
    if (current !== generation) return

    let health: BackendHealthOut
    try {
      health = await Service.getHealthApiCoreHealthGet()
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`读取后台初始化状态失败，本次不再检查: ${errorMsg}`)
      return
    }
    if (current !== generation) return

    const outcome = resolveBackgroundInit(health)
    if (outcome.kind === 'pending') continue
    showOutcome(outcome)
    return
  }
  logger.warn('后端后台初始化长时间未结束，本次不再等待')
}

/** 作废进行中的检查（幂等），用于生命周期释放。 */
export function cancelBackgroundInitCheck(): void {
  generation++
}
