import { expect, test } from './fixtures'
import type { Page, WebSocket } from '@playwright/test'

// 后端端口由环境变量注入，保持与 init.pw.ts / real-integration.pw.ts 一致
const backendUrl = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`

// 主 WebSocket 在应用 bootstrap（appEntry → connectWithRetry）阶段就已建立，
// 而 page.on('websocket') 不会回溯已发生的事件，因此监听必须先于首次导航注册。
function trackMainWebSockets(page: Page): WebSocket[] {
  const sockets: WebSocket[] = []
  page.on('websocket', ws => {
    if (ws.url().includes('/api/core/ws')) {
      sockets.push(ws)
    }
  })
  return sockets
}

// 第 after 个之后的连接（新一轮连接）已建立且仍未关闭
function lastMainSocketOpen(sockets: WebSocket[], after: number): boolean {
  return sockets.length > after && !sockets[sockets.length - 1].isClosed()
}

// 曾有三条用例（页面导航保状态、空闲刷新重连、断线重连）都在做「刷新后等新连接」，
// 断言完全相同且刷新走的是全新 bootstrap，并没有驱动 scheduleReconnect 的退避重连逻辑
// （那条路径由 frontend/src/services/websocket/connection.test.ts 覆盖），故合并为一条。
test.describe('@recovery websocket resilience', () => {
  test('reloads the page and re-establishes the main WebSocket', async ({ app, page }) => {
    const sockets = trackMainWebSockets(page)

    await app.goto('/scheduler')

    // 记录任务控制台的初始状态：侧栏文字先于懒加载的调度台渲染，
    // 必须先等页面内容（有标签页渲染卡片，无标签页渲染空态）再取样，否则会把空列表当基线
    await expect(page.locator('.task-unified-card, .empty-tab-content').first()).toBeVisible()
    const taskControls = page.locator('.task-control')
    const initialCount = await taskControls.count()

    // 基线必须在刷新前采样：刷新后新建的连接才算「重连」
    await expect.poll(() => lastMainSocketOpen(sockets, 0), { timeout: 5000 }).toBe(true)
    const initialSocketCount = sockets.length

    await page.reload()
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    await expect
      .poll(() => lastMainSocketOpen(sockets, initialSocketCount), { timeout: 5000 })
      .toBe(true)

    // 刷新后要等页面内容重新渲染，用自动重试断言避免采样到加载中的空列表；
    // 数量不变说明没有留下上一次会话的任务卡片
    await expect(page.locator('.task-unified-card, .empty-tab-content').first()).toBeVisible()
    await expect(taskControls).toHaveCount(initialCount)

    await app.evidence('recovery-reload-reconnected')
  })

  test('handles backend restart gracefully', async ({ app, page }) => {
    // 这条用例故意让健康检查失败，属于被测行为本身：先声明出来，
    // 否则 fixtures 的兜底断言会把它当成「页面出现不该有的错误」。
    // 后台初始化轮询在同一个窗口期刷出的 Network Error 警告同理。
    app.ignore({
      request: [/\/api\/core\/health$/],
      warning: [/\[后台初始化\] 读取后台初始化状态失败/],
    })
    const sockets = trackMainWebSockets(page)

    await app.goto('/home')

    // 记录初始健康状态
    const healthResponse = await page.request.get(`${backendUrl}/api/core/health`)
    expect(healthResponse.ok()).toBeTruthy()

    // 模拟后端不可用：拦截应用自身发出的健康检查（应用侧请求走 page.route）
    let abortedChecks = 0
    await page.route('**/api/core/health', route => {
      abortedChecks++
      route.abort('failed')
    })

    // 后端不可用时刷新：应用应保持可用，不出现白屏
    await page.reload()
    await expect(page.locator('.sider-content')).toBeVisible()

    // 轮询确认应用确实发起了健康检查并被拦下
    await expect.poll(() => abortedChecks, { timeout: 10000 }).toBeGreaterThan(0)

    await app.evidence('recovery-backend-restart')

    // 后端恢复：解除拦截后应用应重新连上 WebSocket 并成功拿到健康状态
    await page.unroute('**/api/core/health')
    const recoveredHealth = page.waitForResponse(
      response => response.url().includes('/api/core/health'),
      { timeout: 15000 }
    )
    const socketsBeforeRecovery = sockets.length
    await page.reload()
    await expect(page.locator('.sider-content')).toBeVisible()
    expect((await recoveredHealth).ok()).toBeTruthy()
    await expect
      .poll(() => lastMainSocketOpen(sockets, socketsBeforeRecovery), { timeout: 5000 })
      .toBe(true)
  })
})
