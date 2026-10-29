import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// 设置页「Interface」标签的「隐藏关闭按钮」复选框对应 UI.IfHideCloseButton，
// 保存路径为 POST /api/setting/update。
const closeButtonCheckbox = (page: Page) =>
  page.getByRole('checkbox', { name: 'Hide the close button', exact: true })

const waitForSettingsLoad = async (page: Page) => {
  const response = await page.waitForResponse(
    response =>
      response.url().endsWith('/api/setting/get') &&
      response.request().method() === 'POST' &&
      response.ok(),
    { timeout: 10000 }
  )
  const payload = (await response.json()) as {
    data: { UI?: { IfHideCloseButton?: boolean } }
  }
  // 复选框会先以未勾选状态渲染，等配置载入后再读取初始值。
  await expect(closeButtonCheckbox(page)).toBeChecked({
    checked: payload.data.UI?.IfHideCloseButton === true,
  })
}

const waitForSave = (page: Page, ok: boolean) =>
  page.waitForResponse(
    response =>
      response.url().endsWith('/api/setting/update') &&
      response.request().method() === 'POST' &&
      response.ok() === ok,
    { timeout: 10000 }
  )

test.describe('@settings persistence', () => {
  test('saves settings and persists after page reload', async ({ app, page }) => {
    const loaded = waitForSettingsLoad(page)
    await app.goto('/settings')
    await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible()
    await loaded

    // 修改设置：隐藏关闭按钮。
    const initialState = await closeButtonCheckbox(page).isChecked()
    const nextState = !initialState

    const saved = waitForSave(page, true)
    // 受控复选框会在保存成功后更新，单击后用重试断言等待状态提交。
    await closeButtonCheckbox(page).click()
    await saved

    // 验证状态已改变
    await expect(closeButtonCheckbox(page)).toBeChecked({ checked: nextState })

    await app.evidence('settings-modified')

    // 刷新页面，验证持久化
    const reloaded = waitForSettingsLoad(page)
    await page.reload()
    await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible()
    await reloaded
    await expect(closeButtonCheckbox(page)).toBeChecked({ checked: nextState })

    await app.evidence('settings-persisted')

    // 恢复原状态，避免影响后续用例
    const restored = waitForSave(page, true)
    await closeButtonCheckbox(page).click()
    await restored
    await expect(closeButtonCheckbox(page)).toBeChecked({ checked: initialState })
  })

  test('handles save failure gracefully', async ({ app, page }) => {
    const loaded = waitForSettingsLoad(page)
    await app.goto('/settings')
    await loaded
    const initialState = await closeButtonCheckbox(page).isChecked()

    // 拦截保存请求，模拟后端 500
    // 跨域 POST 会先走 OPTIONS 预检：预检放行，500 响应保留 CORS 头，
    // 这样才是「服务端失败」而不是「跨域失败被浏览器拦下」。
    await page.route('**/api/setting/update', route => {
      if (route.request().method() === 'OPTIONS') {
        route.continue()
        return
      }
      route.fulfill({
        status: 500,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
        body: JSON.stringify({ code: 500, status: 'error', message: 'Internal server error' }),
      })
    })

    const failed = waitForSave(page, false)
    await closeButtonCheckbox(page).click()
    await failed

    // 等待用户可见的错误提示
    await expect(page.locator('.ant-message-error')).toHaveCount(1)
    await expect(page.locator('.ant-message-error')).toContainText('Internal server error')

    // 界面不假装成功：控件保持原值
    await expect(closeButtonCheckbox(page)).toBeChecked({ checked: initialState })

    await app.evidence('settings-save-failed')

    // 移除拦截后刷新，确认失败的值没有被持久化
    await page.unroute('**/api/setting/update')
    const reloaded = waitForSettingsLoad(page)
    await page.reload()
    await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible()
    await reloaded
    await expect(closeButtonCheckbox(page)).toBeChecked({ checked: initialState })
  })
})
