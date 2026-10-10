import { expect, test } from './fixtures'

test.describe('@queue persistence', () => {
  test('creates, renames, configures, and reloads a queue', async ({ app, page }) => {
    const queueUpdateResponse = () =>
      page.waitForResponse(
        response =>
          response.url().endsWith('/api/queue/update') &&
          response.request().method() === 'POST' &&
          response.ok()
      )

    await app.goto('/queue')
    await expect(page.getByText('No queues', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: 'New queue' }).click()
    await expect(page.getByRole('button', { name: /New queue|New scheduling queue/ })).toBeVisible()
    const queueTitle = page.locator('.queue-title-text')
    await expect(queueTitle).toBeVisible()
    await page.locator('.queue-edit-btn').click()
    const nameInput = page.locator('.queue-title-input')
    await nameInput.fill('PR 队列验证')
    const renameResponse = queueUpdateResponse()
    await nameInput.press('Enter')
    await renameResponse
    await expect(queueTitle).toHaveText('PR 队列验证')

    const startupSelect = page
      .locator('.form-item-vertical')
      .filter({ hasText: 'Run at startup' })
      .locator('.ant-select-selector')
    await startupSelect.click()
    const alwaysResponse = queueUpdateResponse()
    await page
      .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
      .filter({ hasText: 'Run every time' })
      .click()
    await alwaysResponse
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

    await startupSelect.click()
    const neverResponse = queueUpdateResponse()
    await page
      .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
      .filter({ hasText: 'Never' })
      .click()
    await neverResponse
    await expect(page.locator('.ant-select-selection-item', { hasText: 'Never' })).toBeVisible()
  })
})
