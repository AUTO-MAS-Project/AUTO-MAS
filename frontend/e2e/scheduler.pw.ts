import { expect, test } from './fixtures'

test.describe('@scheduler safeguards', () => {
  test('keeps an empty dispatch safe and manages idle run panels', async ({ app, page }) => {
    const taskOptionsResponse = page.waitForResponse(
      response =>
        response.url().includes('/api/info/combox/task') && response.request().method() === 'POST'
    )

    await app.goto('/scheduler')

    const response = await taskOptionsResponse
    expect(response.ok()).toBeTruthy()
    const payload = await response.json()
    expect(payload.code).toBe(200)
    expect(payload.data?.[0]).toMatchObject({ label: '未选择', value: null })

    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()
    const runButtons = page.locator('.task-control .ant-btn')
    await expect(runButtons).toHaveCount(1)
    await expect(runButtons.first()).toBeDisabled()
    await expect(page.locator('.overview-panel .empty-image')).toBeVisible()
    await expect(page.locator('.log-panel .empty-image')).toBeVisible()

    await page.locator('.tab-add-btn').click()
    await expect(page.locator('.ant-tabs-tab')).toHaveCount(2)
    await expect(page.locator('.task-control .ant-btn')).toHaveCount(2)
    await expect(page.locator('.task-control .ant-btn').last()).toBeDisabled()
    await expect(page.locator('.tab-remove-btn')).toBeEnabled()

    await page.locator('.tab-remove-btn').click()
    await expect(page.getByText('Close idle consoles', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Close it', exact: true }).click()
    await expect(page.getByText('Close idle consoles', { exact: true })).toBeHidden()
    await expect(page.locator('.ant-tabs-tab')).toHaveCount(1)

    await app.evidence('scheduler-empty-protection')
  })
})
