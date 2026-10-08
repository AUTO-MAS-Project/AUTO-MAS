import { expect, test } from './fixtures'

test.describe('@smoke navigation', () => {
  test('opens the core user routes from a clean profile', async ({ app, page }) => {
    await app.goto('/home')
    await expect(page.locator('.home-title')).toBeVisible()

    for (const [route, heading] of [
      ['/plans', 'Plans'],
      ['/queue', 'Queue'],
      ['/scheduler', 'Scheduler'],
      ['/history', 'History'],
      ['/settings', 'Settings'],
    ] as const) {
      await app.goto(route)
      await expect(page).toHaveURL(new RegExp(`#${route}$`))
      await expect(page.getByText(heading, { exact: true }).first()).toBeVisible()
    }

    await app.evidence('core-navigation')
  })
})
