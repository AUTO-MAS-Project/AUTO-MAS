import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// 被驱动的通知投递路径（app/api/setting.py / app/core/notify.py）：
//   界面新建、配置、启停、删除 Webhook —— /api/setting/webhook/*
//   界面「发送测试通知」        —— POST /api/setting/test_notify → send_test_notification()
//                                  → dispatch() → webhook 渠道发送
// 系统通知渠道另有一条用例：它没有 HTTP 回执，只能从后端日志确认走到系统渠道
// （Notify.IfPushPlyer 默认 False，渠道在 targets() 阶段就被 enable_field 排除，
// app/models/notification_channel.py:119），因此 test_notify 的返回码单独不能证明
// Webhook 送达，Webhook 用例一律以接收端的实际收包为准。

const backendUrl = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`
const apiUrl = (path: string) => `${backendUrl}${path}`

const testTitle = 'AUTO-MAS测试通知'
// 与前端预设、DEFAULT_WEBHOOK_TEMPLATE 同形
const webhookTemplate = '{"title": "{title}", "content": "{content}"}'

/** 本地接收端保留目标路径与正文，可切换失败响应验证用户重试。 */
const startReceiver = async () => {
  const requests: { url: string; body: string }[] = []
  let status = 200
  const server = createServer((request, response) => {
    const chunks: Buffer[] = []
    request.on('data', (chunk: Buffer) => chunks.push(chunk))
    request.on('end', () => {
      requests.push({ url: request.url ?? '', body: Buffer.concat(chunks).toString('utf8') })
      response.writeHead(status, { 'Content-Type': 'application/json' })
      response.end('{}')
    })
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = (server.address() as AddressInfo).port
  return {
    url: `http://127.0.0.1:${port}/e2e-hook`,
    requests,
    respondWith: (next: number) => {
      status = next
    },
    close: () => new Promise<void>(resolve => server.close(() => resolve())),
  }
}

const postApi = async (page: Page, path: string, data: unknown = {}) => {
  const response = await page.request.post(apiUrl(path), { data, timeout: 15_000 })
  const body = (await response.json()) as { code?: number; message?: string; webhookId?: string }
  return body
}

const sendTest = async (page: Page) => {
  const sent = page.waitForResponse(
    response =>
      response.url().endsWith('/api/setting/test_notify') && response.request().method() === 'POST',
    { timeout: 15_000 }
  )
  await page.getByRole('button', { name: 'Send a test notification' }).click()
  return (await (await sent).json()) as { code?: number; message?: string }
}

const clickSendTest = async (app: { goto: (route: string) => Promise<void> }, page: Page) => {
  const close = page
    .locator('.notify-channel-modal .modal-head')
    .getByRole('button', { name: 'Close', exact: true })
  if (await close.isVisible()) await close.click()
  await app.goto('/settings')
  await page.getByRole('tab', { name: 'Notifications' }).click()
  return sendTest(page)
}

const webhookResponse = (page: Page, action: string) =>
  page.waitForResponse(
    response =>
      response.url().endsWith(`/api/setting/webhook/${action}`) &&
      response.request().method() === 'POST'
  )

const openWebhooks = async (app: { goto: (route: string) => Promise<void> }, page: Page) => {
  await app.goto('/settings')
  await page.reload()
  await page.getByRole('tab', { name: 'Notifications' }).click()
  await page.getByRole('button', { name: /Custom webhook/ }).click()
  await expect(page.locator('.notify-channel-modal .webhook-manager')).toBeVisible()
}

const webhookRow = (page: Page, name = 'E2E Webhook') =>
  page.locator('.webhook-item').filter({ has: page.getByText(name, { exact: true }) })

test.describe('@notify @webhook UI channel', () => {
  test.skip(
    process.env.AUTO_MAS_E2E_IN_PLACE === '1' || process.env.AUTO_MAS_E2E_REAL === '1',
    '全局通知配置与投递仅在普通隔离模式验证'
  )
  let receiver: Awaited<ReturnType<typeof startReceiver>>
  let webhookIds: string[]

  test.beforeEach(async () => {
    receiver = await startReceiver()
    webhookIds = []
  })

  test.afterEach(async ({ page }) => {
    try {
      for (const webhookId of webhookIds) {
        await postApi(page, '/api/setting/webhook/delete', { webhookId })
      }
    } finally {
      await receiver.close()
    }
  })

  const createWebhook = async (app: { goto: (route: string) => Promise<void> }, page: Page) => {
    await openWebhooks(app, page)
    await page.getByRole('button', { name: /Add a webhook$/ }).click()
    const dialog = page.getByRole('dialog', { name: 'Add a webhook', exact: true })
    await dialog.getByPlaceholder('Enter a webhook name').fill('E2E Webhook')
    await dialog.getByLabel('Webhook URL', { exact: true }).fill(receiver.url)
    await dialog.locator('textarea').fill(webhookTemplate)
    const added = webhookResponse(page, 'add')
    const updated = webhookResponse(page, 'update')
    await dialog.getByRole('button', { name: /^添\s*加$/ }).click()
    const result = await (await added).json()
    expect(result.code).toBe(200)
    expect(result.webhookId).toBeTruthy()
    webhookIds.push(result.webhookId)
    expect((await (await updated).json()).code).toBe(200)
    await expect(dialog).toBeHidden()
    await expect(webhookRow(page)).toContainText(receiver.url)
  }

  test('creates and edits a webhook through the UI and delivers to the saved destination', async ({
    app,
    page,
  }) => {
    await createWebhook(app, page)
    const body = await clickSendTest(app, page)
    expect(body.code, JSON.stringify(body)).toBe(200)
    expect(String(body.message)).toContain('E2E Webhook')
    expect(receiver.requests).toHaveLength(1)
    expect(receiver.requests[0]!.url).toBe('/e2e-hook')
    const payload = JSON.parse(receiver.requests[0]!.body) as { title?: string; content?: string }
    expect(payload.title).toBe(testTitle)
    // 正文来自 send_test_notification 的固定文案，说明这条确实是测试通知而不是别的推送
    expect(String(payload.content)).toContain('AUTO-MAS 的通知功能已经正确配置')

    await openWebhooks(app, page)
    await webhookRow(page).getByRole('button', { name: 'Edit', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Edit Webhook', exact: true })
    await dialog.getByPlaceholder('Enter a webhook name').fill('E2E Webhook edited')
    await dialog.getByLabel('Webhook URL', { exact: true }).fill(`${receiver.url}-edited`)
    const editedTemplate = '{"title":"{title}","content":"{content}","marker":"edited"}'
    await dialog.locator('textarea').fill(editedTemplate)
    const updated = webhookResponse(page, 'update')
    await dialog.getByRole('button', { name: /^更\s*新$/ }).click()
    expect((await (await updated).json()).code).toBe(200)
    await expect(dialog).toBeHidden()

    await openWebhooks(app, page)
    await expect(webhookRow(page)).toHaveCount(0)
    await expect(webhookRow(page, 'E2E Webhook edited')).toContainText(`${receiver.url}-edited`)
    await webhookRow(page, 'E2E Webhook edited')
      .getByRole('button', { name: 'Edit', exact: true })
      .click()
    await expect(dialog.getByPlaceholder('Enter a webhook name')).toHaveValue('E2E Webhook edited')
    await expect(dialog.getByLabel('Webhook URL', { exact: true })).toHaveValue(
      `${receiver.url}-edited`
    )
    await expect(dialog.locator('textarea')).toHaveValue(editedTemplate)
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(dialog).toBeHidden()

    const edited = await clickSendTest(app, page)
    expect(edited.code, JSON.stringify(edited)).toBe(200)
    expect(receiver.requests).toHaveLength(2)
    expect(receiver.requests[1]!.url).toBe('/e2e-hook-edited')
    expect(JSON.parse(receiver.requests[1]!.body)).toMatchObject({
      title: testTitle,
      marker: 'edited',
    })
    await app.evidence('notify-webhook-edited-delivered')
  })

  test('disables, reenables and deletes a webhook through the UI', async ({ app, page }) => {
    await createWebhook(app, page)
    const disabled = webhookResponse(page, 'update')
    await webhookRow(page).getByRole('switch').click()
    expect((await (await disabled).json()).code).toBe(200)
    await expect(webhookRow(page).getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    const body = await clickSendTest(app, page)
    // 关闭的 Webhook 连投递目标都不是，所以后端直接回 400「没有已启用的通知渠道」，
    // 无需等待即可确认接收端没收到东西。
    expect(body.code, JSON.stringify(body)).toBe(400)
    expect(String(body.message)).toContain('没有已启用的通知渠道')
    expect(receiver.requests).toHaveLength(0)

    await openWebhooks(app, page)
    await expect(webhookRow(page).getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    const enabled = webhookResponse(page, 'update')
    await webhookRow(page).getByRole('switch').click()
    expect((await (await enabled).json()).code).toBe(200)
    await expect(webhookRow(page).getByRole('switch')).toHaveAttribute('aria-checked', 'true')
    expect((await clickSendTest(app, page)).code).toBe(200)
    expect(receiver.requests).toHaveLength(1)

    await openWebhooks(app, page)
    await webhookRow(page).getByRole('button', { name: 'Delete', exact: true }).click()
    const confirmation = page.getByRole('dialog').filter({ hasText: 'Confirm deletion' })
    const deleted = webhookResponse(page, 'delete')
    await confirmation.getByRole('button', { name: 'Confirm deletion', exact: true }).click()
    expect((await (await deleted).json()).code).toBe(200)
    await expect(webhookRow(page)).toHaveCount(0)
    await openWebhooks(app, page)
    await expect(webhookRow(page)).toHaveCount(0)
    expect((await clickSendTest(app, page)).code).toBe(400)
    expect(receiver.requests).toHaveLength(1)
    webhookIds = []
    await app.evidence('notify-webhook-deleted')
  })

  test('reports receiver failure and lets the user retry delivery', async ({ app, page }) => {
    await createWebhook(app, page)
    receiver.respondWith(503)
    const failed = await clickSendTest(app, page)
    expect(failed.code, JSON.stringify(failed)).toBe(500)
    await expect(page.locator('.ant-message-warning')).toContainText('E2E Webhook')
    await expect(page.locator('.ant-message-success')).toHaveCount(0)
    expect(receiver.requests.length).toBeGreaterThan(0)
    const failedAttempts = receiver.requests.length
    await app.evidence('notify-webhook-rejected')

    receiver.respondWith(200)
    const retried = await sendTest(page)
    expect(retried.code, JSON.stringify(retried)).toBe(200)
    await expect(page.locator('.ant-message-success')).toContainText('E2E Webhook')
    expect(receiver.requests).toHaveLength(failedAttempts + 1)
    expect(JSON.parse(receiver.requests[failedAttempts]!.body)).toMatchObject({ title: testTitle })
  })
})

/** 后端日志：系统通知没有回执，只能靠它在 app/core 与 system 渠道里留下的痕迹判断。 */
const readBackendLog = async () => {
  const dataRoot = process.env.AUTO_MAS_E2E_DATA_ROOT
  if (!dataRoot) throw new Error('缺少 AUTO_MAS_E2E_DATA_ROOT，读不到后端日志')
  return readFile(path.join(dataRoot, 'debug', 'app.log'), 'utf8').catch(() => '')
}

test.describe('@notify system channel', () => {
  test('pushes the test notification to the Windows system channel', async ({ app, page }) => {
    // 该用例会真的弹出一次 Windows 通知，这正是被测行为。
    test.skip(process.platform !== 'win32', '系统通知渠道只有 Windows 实现')

    const enabled = await postApi(page, '/api/setting/update', {
      data: { Notify: { IfPushPlyer: true } },
    })
    expect(enabled, JSON.stringify(enabled)).toMatchObject({ code: 200 })
    try {
      const body = await clickSendTest(app, page)

      // 全程没有 HTTP 回执，只有系统渠道成功才会进 succeeded 列表
      expect(body.code, JSON.stringify(body)).toBe(200)
      expect(String(body.message)).toContain('系统')

      // 系统渠道的发送日志（app/notification_channels/system/transport.py:82）证明
      // 确实派发到了系统通知，而不是被空目标或异常吞掉。
      await expect
        .poll(async () => (await readBackendLog()).includes(`推送系统通知: ${testTitle}`), {
          timeout: 15_000,
        })
        .toBe(true)

      await app.evidence('notify-system-sent')
    } finally {
      const restored = await postApi(page, '/api/setting/update', {
        data: { Notify: { IfPushPlyer: false } },
      })
      expect(restored, JSON.stringify(restored)).toMatchObject({ code: 200 })
    }
  })
})
