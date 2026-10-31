import { expect, test } from './fixtures'
import type { Page, WebSocket, WebSocketRoute } from '@playwright/test'
import type { WSTaskCompletedData } from '../src/services/websocket/types'
import { observeMainConnection } from './socket-recovery'

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
  test('reconnects without reload and receives a real unconfigured-task result', async ({
    app,
    page,
  }) => {
    const completedTasks = new Map<string, { data: WSTaskCompletedData; route: WebSocketRoute }>()
    const connection = await observeMainConnection(page, (frame, route) => {
      const message = JSON.parse(frame.toString()) as {
        id: string
        type: string
        data: WSTaskCompletedData
      }
      if (message.type === 'task.completed')
        completedTasks.set(message.id, { data: message.data, route })
    })
    const post = async (path: string, data: unknown) => {
      const response = await page.request.post(`${backendUrl}${path}`, { data })
      expect(response.ok()).toBe(true)
      const body = await response.json()
      expect(body.code).toBe(200)
      return body
    }
    const { scriptId } = await post('/api/scripts/add', { type: 'MAA' })
    let userId: string | undefined
    try {
      await post('/api/scripts/update', { scriptId, data: { Info: { Name: 'Recovery probe' } } })
      userId = (await post('/api/scripts/user/add', { scriptId })).userId
      await post('/api/scripts/user/update', {
        scriptId,
        userId,
        data: { Info: { Name: 'Recovery account', Status: true, RemainedDay: -1 } },
      })
      await app.goto('/scheduler')
      const control = page.locator('.task-control')
      await expect(control).toHaveCount(1)
      const recovered = await connection.reconnect()
      await control.locator('.ant-select-selector').first().click()
      await page
        .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: 'Recovery probe' })
        .click()
      const started = page.waitForResponse(
        response =>
          response.url().endsWith('/api/dispatch/start') && response.request().method() === 'POST'
      )
      await control.getByRole('button', { name: /Run$/ }).click()
      const response = await started
      expect(response.ok()).toBe(true)
      const accepted = await response.json()
      expect(accepted.code).toBe(200)
      // 没有安装路径和模拟器的隔离任务应失败；真实消息只用于证明恢复后的双向链路。
      await expect
        .poll(
          () =>
            completedTasks
              .get(accepted.taskId)
              ?.data.task_info.find(script => script.script_id === scriptId)?.status,
          { timeout: 30_000 }
        )
        .toBe('异常')
      expect(completedTasks.get(accepted.taskId)?.route).toBe(recovered.route)
      expect(recovered.received).toBeGreaterThan(0)
      await expect(page.locator('.tab-status.ant-tag-error')).toBeVisible()
      await expect(control.getByRole('button', { name: /Run$/ })).toBeEnabled()
      await expect(control).toHaveCount(1)
      await app.evidence('recovery-without-reload')
    } finally {
      if (userId) await post('/api/scripts/user/delete', { scriptId, userId })
      await post('/api/scripts/delete', { scriptId })
    }
  })

  test('recovers after health requests fail during page reload', async ({ app, page }) => {
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

    await app.evidence('recovery-health-request-failure')

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
