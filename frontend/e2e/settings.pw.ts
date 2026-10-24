import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// 被驱动的设置项：设置页「Interface」标签的「隐藏关闭按钮」开关。
// 控件见 frontend/src/views/setting/TabBasic.vue 的 a-switch（字段 UI.IfHideCloseButton），
// 保存路径为 POST /api/setting/update（frontend/src/composables/useSettingsApi.ts:38-65），
// 后端落盘见 app/api/setting.py:177-198 与 app/core/config.py:3689-3704。
const closeButtonField = (page: Page) =>
  page.locator('.form-item-vertical').filter({ hasText: 'Hide the close button' })

const closeButtonSwitch = (page: Page) => closeButtonField(page).locator('.ant-switch')

const isChecked = async (page: Page) =>
  (await closeButtonSwitch(page).getAttribute('class'))?.includes('ant-switch-checked') ?? false

const expectChecked = async (page: Page, checked: boolean) => {
  if (checked) {
    await expect(closeButtonSwitch(page)).toHaveClass(/ant-switch-checked/)
  } else {
    await expect(closeButtonSwitch(page)).not.toHaveClass(/ant-switch-checked/)
  }
}

const waitForSave = (page: Page, ok: boolean) =>
  page.waitForResponse(
    response =>
      response.url().endsWith('/api/setting/update') &&
      response.request().method() === 'POST' &&
      response.ok() === ok,
    { timeout: 10000 }
  )

// a-switch 是翻转控件：点击前先读当前状态，只在需要时点击。
const setCloseButton = async (page: Page, checked: boolean) => {
  if ((await isChecked(page)) !== checked) {
    await closeButtonSwitch(page).click()
  }
}

test.describe('@settings persistence', () => {
  test('saves settings and persists after page reload', async ({ app, page }) => {
    await app.goto('/settings')
    await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible()

    // 修改设置：隐藏关闭按钮（开关渲染出来即表示设置已加载）
    await expect(closeButtonSwitch(page)).toBeVisible()
    const initialState = await isChecked(page)

    const saved = waitForSave(page, true)
    await closeButtonSwitch(page).click()
    await saved

    // 验证状态已改变
    await expectChecked(page, !initialState)

    await app.evidence('settings-modified')

    // 刷新页面，验证持久化
    await page.reload()
    await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible()
    await expectChecked(page, !initialState)

    await app.evidence('settings-persisted')

    // 恢复原状态，避免影响后续用例
    const restored = waitForSave(page, true)
    await closeButtonSwitch(page).click()
    await restored
    await expectChecked(page, initialState)
  })

  test('handles save failure gracefully', async ({ app, page }) => {
    // 保存接口被故意打成 500，属于被测行为：5xx 兜底断言按接口放行
    app.ignore({ serverError: [/\/api\/setting\/update$/] })
    await app.goto('/settings')
    await expect(closeButtonSwitch(page)).toBeVisible()
    const initialState = await isChecked(page)

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
    await setCloseButton(page, !initialState)
    await failed

    // 等待用户可见的错误提示
    await expect(page.locator('.ant-message-error')).toHaveCount(1)
    await expect(page.locator('.ant-message-error')).toContainText('Internal server error')

    // 界面不假装成功：开关受控于设置对象，保存失败后保持原值
    await expectChecked(page, initialState)

    await app.evidence('settings-save-failed')

    // 移除拦截后刷新，确认失败的值没有被持久化
    await page.unroute('**/api/setting/update')
    await page.reload()
    await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible()
    await expectChecked(page, initialState)
  })
})
