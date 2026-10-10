import { expect, test } from './fixtures'

test.describe('@settings persistence', () => {
  test('saves settings and persists after page reload', async ({ app, page }) => {
    await app.goto('/settings')
    await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible()

    // 修改设置：通知开关
    const notifySwitch = page.locator('.ant-switch').first()
    const initialState = await notifySwitch.getAttribute('aria-checked')
    await notifySwitch.click()

    // 等待保存请求完成
    const saveResponse = await page.waitForResponse(
      response =>
        response.url().includes('/api/setting/update') &&
        response.request().method() === 'POST' &&
        response.ok(),
      { timeout: 5000 }
    )
    expect(saveResponse.ok()).toBeTruthy()

    // 验证状态已改变
    const newState = await notifySwitch.getAttribute('aria-checked')
    expect(newState).not.toBe(initialState)

    await app.evidence('settings-modified')

    // 刷新页面，验证持久化
    await page.reload()
    await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible()

    const persistedState = await page.locator('.ant-switch').first().getAttribute('aria-checked')
    expect(persistedState).toBe(newState)

    await app.evidence('settings-persisted')

    // 恢复原状态
    await page.locator('.ant-switch').first().click()
    await page.waitForResponse(
      response => response.url().includes('/api/setting/update'),
      { timeout: 5000 }
    )
  })

  test('handles save failure gracefully', async ({ app, page }) => {
    await app.goto('/settings')

    // 拦截保存请求，模拟失败
    await page.route('**/api/setting/update', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 500,
          status: 'error',
          message: 'Internal server error'
        })
      })
    })

    const notifySwitch = page.locator('.ant-switch').first()
    const initialState = await notifySwitch.getAttribute('aria-checked')

    await notifySwitch.click()

    // 等待错误提示
    await expect(page.locator('.ant-message-error, .ant-notification-error')).toBeVisible({
      timeout: 3000
    })

    // 验证状态已回滚到初始状态
    const finalState = await notifySwitch.getAttribute('aria-checked')
    expect(finalState).toBe(initialState)

    await app.evidence('settings-save-failed')

    // 移除拦截
    await page.unroute('**/api/setting/update')
  })
})
