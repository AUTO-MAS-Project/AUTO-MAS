import { expect, test } from './fixtures'
import type { WebSocket } from '@playwright/test'

test.describe('@recovery websocket resilience', () => {
  test('maintains UI state across page navigation', async ({ app, page }) => {
    // 访问队列页面并创建队列
    await app.goto('/queue')
    await page.getByRole('button', { name: 'New queue' }).click()
    await expect(page.locator('.queue-title-text')).toBeVisible()

    // 记录队列标题
    const queueTitle = await page.locator('.queue-title-text').first().innerText()

    // 导航到其他页面
    await app.goto('/scheduler')
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 返回队列页面，验证状态保持
    await app.goto('/queue')
    const restoredTitle = await page.locator('.queue-title-text').first().innerText()
    expect(restoredTitle).toBe(queueTitle)

    await app.evidence('recovery-navigation-state')
  })

  test('handles page reload during idle state', async ({ app, page }) => {
    await app.goto('/scheduler')
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 验证 WebSocket 已连接
    let wsConnected = false
    page.on('websocket', ws => {
      if (ws.url().includes('/api/core/ws')) {
        wsConnected = true
      }
    })

    await page.waitForTimeout(1000)
    expect(wsConnected).toBeTruthy()

    await app.evidence('recovery-before-reload')

    // 刷新页面
    await page.reload()
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 验证 WebSocket 重新连接
    let wsReconnected = false
    const wsPromise = new Promise<void>(resolve => {
      page.on('websocket', ws => {
        if (ws.url().includes('/api/core/ws')) {
          wsReconnected = true
          resolve()
        }
      })
    })

    await Promise.race([wsPromise, page.waitForTimeout(5000)])
    expect(wsReconnected).toBeTruthy()

    await app.evidence('recovery-after-reload')
  })

  test('reconnects WebSocket after temporary disconnection', async ({ app, page }) => {
    await app.goto('/scheduler')

    const sockets: WebSocket[] = []
    page.on('websocket', ws => {
      if (ws.url().includes('/api/core/ws')) {
        sockets.push(ws)
      }
    })

    // 等待初始连接
    await page.waitForTimeout(2000)
    expect(sockets.length).toBeGreaterThan(0)

    const initialSocket = sockets[sockets.length - 1]
    expect(initialSocket.isClosed()).toBe(false)

    await app.evidence('recovery-ws-connected')

    // 模拟断线：刷新页面强制断开 WebSocket
    await page.reload()
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 等待重连
    await page.waitForTimeout(3000)

    // 验证有新的 WebSocket 连接
    expect(sockets.length).toBeGreaterThan(1)
    const reconnectedSocket = sockets[sockets.length - 1]
    expect(reconnectedSocket.isClosed()).toBe(false)

    await app.evidence('recovery-ws-reconnected')
  })

  test('handles backend restart gracefully', async ({ app, page }) => {
    await app.goto('/home')

    // 记录初始健康状态
    const healthResponse = await page.request.get('http://127.0.0.1:36174/api/core/health')
    expect(healthResponse.ok()).toBeTruthy()

    // 模拟后端不可用（拦截请求返回错误）
    let requestCount = 0
    await page.route('**/api/core/health', route => {
      requestCount++
      if (requestCount <= 3) {
        // 前 3 次请求模拟后端不可用
        route.abort('failed')
      } else {
        // 之后恢复正常
        route.continue()
      }
    })

    // 触发健康检查（通过刷新页面）
    await page.reload()

    // 等待恢复
    await page.waitForTimeout(5000)

    // 验证页面最终恢复正常
    const restored = await page.locator('#app').isVisible()
    expect(restored).toBeTruthy()

    await app.evidence('recovery-backend-restart')

    // 清理拦截
    await page.unroute('**/api/core/health')
  })

  test('preserves task state during WebSocket reconnection', async ({ app, page }) => {
    await app.goto('/scheduler')

    // 记录任务控制台的初始状态
    const taskControls = page.locator('.task-control')
    const initialCount = await taskControls.count()

    // 刷新页面触发重连
    await page.reload()
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()

    // 等待 WebSocket 重连
    await page.waitForTimeout(3000)

    // 验证任务控制台状态恢复
    const restoredCount = await taskControls.count()
    expect(restoredCount).toBe(initialCount)

    await app.evidence('recovery-task-state-preserved')
  })
})
