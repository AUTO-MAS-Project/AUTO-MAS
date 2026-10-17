import { expect, test } from './fixtures'

test.describe('@smoke navigation', () => {
  test('opens the core user routes from a clean profile', async ({ app, page }) => {
    await app.goto('/home')
    await expect(page.locator('.home-title')).toBeVisible()

    // 侧栏也有同名文字，只断言标题会被导航栏满足；必须同时断言页面自身的根节点
    for (const [route, heading, root] of [
      ['/plans', 'Plans', '.plans-main'],
      ['/queue', 'Queue', '.queue-main'],
      ['/scheduler', 'Scheduler', '.scheduler-main'],
      ['/history', 'History', '.history-page'],
      ['/settings', 'Settings', '.settings-container'],
    ] as const) {
      await app.goto(route)
      await expect(page).toHaveURL(new RegExp(`#${route}$`))
      await expect(page.getByText(heading, { exact: true }).first()).toBeVisible()
      await expect(page.locator(root)).toBeVisible()
    }

    await app.evidence('core-navigation')
  })
})
