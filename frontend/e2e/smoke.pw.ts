import { expect, test } from './fixtures'

test.describe('@smoke navigation', () => {
  test('navigates between core pages through the sidebar', async ({ app, page }) => {
    await app.goto('/home')
    await expect(page.locator('.home-title')).toBeVisible()

    // 同时检查菜单状态和页面根节点，避免侧栏文字掩盖页面加载失败。
    for (const [route, heading, root] of [
      ['/plans', 'Plans', '.plans-main'],
      ['/queue', 'Queue', '.queue-main'],
      ['/scheduler', 'Scheduler', '.scheduler-main'],
      ['/history', 'History', '.history-page'],
      ['/settings', 'Settings', '.settings-container'],
      ['/home', 'Home', '.home-title'],
    ] as const) {
      const menu = page
        .getByRole('menuitem')
        .filter({ has: page.getByText(heading, { exact: true }) })
      await menu.click()
      await expect(page).toHaveURL(new RegExp(`#${route}$`))
      await expect(menu).toHaveClass(/ant-menu-item-selected/)
      await expect(page.locator(root)).toBeVisible()
    }

    await app.evidence('core-navigation')
  })
})
