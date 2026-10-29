import type { APIRequestContext } from '@playwright/test'
import type { WSTaskCompletedData } from '../src/services/websocket/types'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
const post = async (request: APIRequestContext, path: string, data: unknown) => {
  const response = await request.post(`${backend}${path}`, { data })
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  expect(body.code).toBe(200)
  return body
}

// Authors may use an installed Chromium without downloading another browser.
if (process.env.AUTO_MAS_E2E_CHROMIUM_PATH) {
  test.use({ launchOptions: { executablePath: process.env.AUTO_MAS_E2E_CHROMIUM_PATH } })
}

test.describe('@maa-update configuration and dispatch', () => {
  test('persists beta selection and reports an unconfigured MAA task as failed', async ({
    app,
    page,
  }) => {
    const completed = new Map<string, WSTaskCompletedData>()
    page.on('websocket', socket => {
      if (new URL(socket.url()).pathname !== '/api/core/ws') return
      socket.on('framereceived', ({ payload }) => {
        const message = JSON.parse(typeof payload === 'string' ? payload : payload.toString()) as {
          type?: string
          id?: string
          data?: WSTaskCompletedData
        }
        if (message.type === 'task.completed' && message.id && message.data) {
          completed.set(message.id, message.data)
        }
      })
    })
    const created = await post(page.request, '/api/scripts/add', { type: 'MAA' })
    const scriptId: string = created.scriptId
    await post(page.request, '/api/scripts/update', {
      scriptId,
      data: { Info: { Name: 'PR1730 MAA' } },
    })
    const user = await post(page.request, '/api/scripts/user/add', { scriptId })
    await post(page.request, '/api/scripts/user/update', {
      scriptId,
      userId: user.userId,
      data: { Info: { Name: 'isolated account', Status: true, RemainedDay: -1 } },
    })

    await app.goto(`/scripts/${scriptId}/edit/maa`)
    const updatePanel = page
      .locator('.form-section')
      .filter({ has: page.getByRole('heading', { name: 'Update takeover', exact: true }) })
    await expect(updatePanel).toBeVisible()
    await updatePanel.locator('.ant-select-selector').click()
    const save = page.waitForResponse(
      response =>
        response.url().endsWith('/api/scripts/update') &&
        response.request().postDataJSON()?.data?.Update?.Channel === 'beta'
    )
    await page.locator('.ant-select-dropdown:visible').getByText('Beta', { exact: true }).click()
    expect((await (await save).json()).code).toBe(200)
    const enable = page.waitForResponse(
      response =>
        response.url().endsWith('/api/scripts/update') &&
        response.request().postDataJSON()?.data?.Update?.TakeoverEnabled === true
    )
    await updatePanel.getByRole('switch').click()
    expect((await (await enable).json()).code).toBe(200)
    await page.reload()
    await expect(updatePanel.locator('.ant-select-selection-item')).toHaveText('Beta')
    await expect(updatePanel.getByRole('switch')).toBeChecked()
    await updatePanel.scrollIntoViewIfNeeded()
    await app.evidence('maa-update-channel-persisted')

    await app.goto('/scheduler')
    const control = page.locator('.task-control').first()
    await control.locator('.ant-select-selector').first().click()
    await page
      .locator('.ant-select-dropdown:visible')
      .locator('.ant-select-item-option-content')
      .filter({ hasText: 'PR1730 MAA' })
      .click()
    const started = page.waitForResponse(
      response =>
        response.url().endsWith('/api/dispatch/start') && response.request().method() === 'POST'
    )
    await control.getByRole('button', { name: /Run$/ }).click()
    const accepted = await (await started).json()
    expect(accepted.code).toBe(200)
    expect(accepted.taskId).toBeTruthy()
    // This isolated profile has no MAA or emulator. It must not claim an upgrade or run succeeded.
    await expect
      .poll(
        () =>
          completed.get(accepted.taskId)?.task_info.find(script => script.script_id === scriptId)
            ?.status,
        { timeout: 30_000 }
      )
      .toBe('异常')
    const saved = await post(page.request, '/api/scripts/get', { scriptId })
    expect(saved.data[scriptId].Update.Channel).toBe('beta')
    expect(saved.data[scriptId].Update.TakeoverEnabled).toBe(true)
    await app.evidence('maa-update-unconfigured-task-failed')
  })
})
