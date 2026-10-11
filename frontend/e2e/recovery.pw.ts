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

test.describe('@recovery websocket resilience', () => {
  test('maintains UI state across page navigation', async ({ app, page }) => {
    // 访问队列页面并创建队列
    await app.goto('/queue')
    const queueTitleText = page.locator('.queue-title-text')
    await expect(queueTitleText).toBeVisible()
    const previousTitle = await queueTitleText.innerText()

    await page.getByRole('button', { name: 'New queue' }).click()
    // 新建后当前队列标题异步切换，等它落到新队列再取样，否则会把上一个队列当成基线
    await expect(queueTitleText).not.toHaveText(previousTitle)
    const queueTitle = await queueTitleText.innerText()

    // 导航到其他页面
    await app.goto('/scheduler')
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 返回队列页面，验证状态保持
    await app.goto('/queue')
    await expect(queueTitleText).toHaveText(queueTitle)

    await app.evidence('recovery-navigation-state')
  })

  test('handles page reload during idle state', async ({ app, page }) => {
    // 监听必须先于首次导航注册，否则捕获不到 bootstrap 阶段建立的连接
    const sockets = trackMainWebSockets(page)

    await app.goto('/scheduler')
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 轮询等待 WebSocket 连接
    await expect.poll(() => lastMainSocketOpen(sockets, 0), { timeout: 5000 }).toBe(true)

    await app.evidence('recovery-before-reload')

    // 刷新页面
    await page.reload()
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 轮询等待刷新后重新建立的 WebSocket 连接
    await expect.poll(() => lastMainSocketOpen(sockets, 1), { timeout: 5000 }).toBe(true)

    await app.evidence('recovery-after-reload')
  })

  test('reconnects WebSocket after temporary disconnection', async ({ app, page }) => {
    // 监听必须先于首次导航注册，否则捕获不到 bootstrap 阶段建立的连接
    const sockets = trackMainWebSockets(page)

    await app.goto('/scheduler')
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 轮询等待初始连接
    await expect.poll(() => lastMainSocketOpen(sockets, 0), { timeout: 5000 }).toBe(true)

    await app.evidence('recovery-ws-connected')

    // 模拟断线：刷新页面强制断开 WebSocket
    await page.reload()
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 轮询等待重连
    await expect.poll(() => lastMainSocketOpen(sockets, 1), { timeout: 5000 }).toBe(true)

    await app.evidence('recovery-ws-reconnected')
  })

  test('handles backend restart gracefully', async ({ app, page }) => {
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

  test('preserves task state during WebSocket reconnection', async ({ app, page }) => {
    // 监听必须先于首次导航注册，否则捕获不到 bootstrap 阶段建立的连接
    const sockets = trackMainWebSockets(page)

    await app.goto('/scheduler')

    // 记录任务控制台的初始状态：侧栏文字先于懒加载的调度台渲染，
    // 必须先等页面内容（有标签页渲染卡片，无标签页渲染空态）再取样，否则会把空列表当基线
    await expect(page.locator('.task-unified-card, .empty-tab-content').first()).toBeVisible()
    const taskControls = page.locator('.task-control')
    const initialCount = await taskControls.count()

    // 基线必须在刷新前采样：刷新后新建的连接才算“重连”
    await expect.poll(() => lastMainSocketOpen(sockets, 0), { timeout: 5000 }).toBe(true)
    const initialSocketCount = sockets.length

    // 刷新页面触发重连
    await page.reload()
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 轮询等待 WebSocket 重连
    await expect
      .poll(() => lastMainSocketOpen(sockets, initialSocketCount), { timeout: 5000 })
      .toBe(true)

    // 验证任务控制台状态恢复：刷新后要等页面内容重新渲染，用自动重试断言避免采样到加载中的空列表
    await expect(page.locator('.task-unified-card, .empty-tab-content').first()).toBeVisible()
    await expect(taskControls).toHaveCount(initialCount)

    await app.evidence('recovery-task-state-preserved')
  })
})
