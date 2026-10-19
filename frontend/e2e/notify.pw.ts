import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// 被驱动的通知投递路径（app/api/setting.py / app/core/notify.py）：
//   新建并配置一条全局自定义 Webhook —— POST /api/setting/webhook/add、/webhook/update
//   界面「发送测试通知」        —— POST /api/setting/test_notify → send_test_notification()
//                                  → dispatch() → webhook 渠道发送
// 断言都落在「本地接收端真的收到/没收到测试通知」上：系统通知默认未启用
// （Notify.IfPushPlyer 默认 False，渠道在 targets() 阶段就被 enable_field 排除），
// 因此 test_notify 的返回码单独不能证明 Webhook 送达。

const backendUrl = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`
const apiUrl = (path: string) => `${backendUrl}${path}`

const testTitle = 'AUTO-MAS测试通知'
// 与前端预设、DEFAULT_WEBHOOK_TEMPLATE 同形
const webhookTemplate = '{"title": "{title}", "content": "{content}"}'

/** 本地接收端：只收请求体，按机器人平台的惯例回 200 + 空 JSON。 */
const startReceiver = async () => {
  const bodies: string[] = []
  const server = createServer((request, response) => {
    const chunks: Buffer[] = []
    request.on('data', (chunk: Buffer) => chunks.push(chunk))
    request.on('end', () => {
      bodies.push(Buffer.concat(chunks).toString('utf8'))
      response.writeHead(200, { 'Content-Type': 'application/json' })
      response.end('{}')
    })
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = (server.address() as AddressInfo).port
  return {
    url: `http://127.0.0.1:${port}/e2e-hook`,
    bodies,
    close: () => new Promise<void>(resolve => server.close(() => resolve())),
  }
}

const postApi = async (page: Page, path: string, data: unknown = {}) => {
  const response = await page.request.post(apiUrl(path), { data, timeout: 15_000 })
  const body = (await response.json()) as { code?: number; message?: string; webhookId?: string }
  return body
}

/** 新建一条只指向本地接收端的 Webhook，返回它在配置里的 ID。 */
const createWebhook = async (page: Page, url: string) => {
  const added = await postApi(page, '/api/setting/webhook/add')
  expect(added.code).toBe(200)
  const webhookId = String(added.webhookId ?? '')
  expect(webhookId).not.toBe('')

  const updated = await postApi(page, '/api/setting/webhook/update', {
    webhookId,
    data: {
      Info: { Name: 'E2E Webhook', Enabled: true },
      Data: { Url: url, Template: webhookTemplate, Method: 'POST' },
    },
  })
  expect(updated, JSON.stringify(updated)).toMatchObject({ code: 200 })
  return webhookId
}

const setWebhookEnabled = async (page: Page, webhookId: string, enabled: boolean) => {
  const updated = await postApi(page, '/api/setting/webhook/update', {
    webhookId,
    data: { Info: { Enabled: enabled } },
  })
  expect(updated, JSON.stringify(updated)).toMatchObject({ code: 200 })
}

const clickSendTest = async (app: { goto: (route: string) => Promise<void> }, page: Page) => {
  await app.goto('/settings')
  await page.getByRole('tab', { name: 'Notifications' }).click()
  const sent = page.waitForResponse(
    response =>
      response.url().endsWith('/api/setting/test_notify') && response.request().method() === 'POST',
    { timeout: 15_000 }
  )
  await page.getByRole('button', { name: 'Send a test notification' }).click()
  return (await (await sent).json()) as { code?: number; message?: string }
}

test.describe('@notify webhook channel', () => {
  let receiver: Awaited<ReturnType<typeof startReceiver>>
  let webhookId = ''

  test.beforeEach(async ({ page }) => {
    receiver = await startReceiver()
    webhookId = await createWebhook(page, receiver.url)
  })

  test.afterEach(async ({ page }) => {
    if (webhookId) await postApi(page, '/api/setting/webhook/delete', { webhookId })
    await receiver.close()
  })

  test('delivers the test notification from the settings page to the configured webhook', async ({
    app,
    page,
  }) => {
    const body = await clickSendTest(app, page)
    expect(body.code, JSON.stringify(body)).toBe(200)
    expect(String(body.message)).toContain('测试通知已提交至')

    await expect.poll(() => receiver.bodies.length, { timeout: 15_000 }).toBeGreaterThan(0)
    const payload = JSON.parse(receiver.bodies[0]) as { title?: string; content?: string }
    expect(payload.title).toBe(testTitle)
    // 正文来自 send_test_notification 的固定文案，说明这条确实是测试通知而不是别的推送
    expect(String(payload.content)).toContain('AUTO-MAS 的通知功能已经正确配置')

    expect(String(body.message)).toContain('E2E Webhook')

    await app.evidence('notify-test-sent')
  })

  test('stops delivering once the webhook is disabled', async ({ app, page }) => {
    await setWebhookEnabled(page, webhookId, false)

    const body = await clickSendTest(app, page)

    // 关闭的 Webhook 连投递目标都不是，所以后端直接回 400「没有已启用的通知渠道」，
    // 无需等待即可确认接收端没收到东西。
    expect(body.code, JSON.stringify(body)).toBe(400)
    expect(String(body.message)).toContain('没有已启用的通知渠道')
    expect(receiver.bodies.length).toBe(0)
  })
})
