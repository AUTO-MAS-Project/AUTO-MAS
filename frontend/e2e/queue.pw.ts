import { expect, test } from './fixtures'

test.describe('@queue persistence', () => {
  test('creates, renames, configures, and reloads a queue', async ({ app, page }) => {
    await app.goto('/queue')
    await expect(page.getByText('No queues', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: 'New queue' }).click()
    await expect(page.getByRole('button', { name: /New queue|New scheduling queue/ })).toBeVisible()
    const queueTitle = page.locator('.queue-title-text')
    await expect(queueTitle).toBeVisible()
    await page.locator('.queue-edit-btn').click()
    const nameInput = page.locator('.queue-title-input')
    await nameInput.fill('PR 队列验证')
    await nameInput.press('Enter')
    await expect(queueTitle).toHaveText('PR 队列验证')

    await page
      .locator('.form-item-vertical')
      .filter({ hasText: 'Run at startup' })
      .locator('.ant-select')
      .click()
    await page.getByText('Run every time', { exact: true }).last().click()
    await expect(
      page.locator('.ant-select-selection-item', { hasText: 'Run every time' })
    ).toBeVisible()

    await app.evidence('queue-configured')
    await app.goto('/home')
    await app.goto('/queue')
    await expect(page.locator('.queue-title-text')).toHaveText('PR 队列验证')
    await expect(
      page.locator('.ant-select-selection-item', { hasText: 'Run every time' })
    ).toBeVisible()
    await app.evidence('queue-reloaded')

    await page
      .locator('.form-item-vertical')
      .filter({ hasText: 'Run at startup' })
      .locator('.ant-select')
      .click()
    await page.getByText('Never', { exact: true }).last().click()
    await expect(page.locator('.ant-select-selection-item', { hasText: 'Never' })).toBeVisible()
  })
})
