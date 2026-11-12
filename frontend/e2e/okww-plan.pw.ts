import { expect, test } from './fixtures'
const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@okww-plan', () => {
  test('global, weekly and rotating plans save the selected date only', async ({ app, page }) => {
    for (const [mode, group, other] of [
      ['ALL', 'ALL', 'Monday'],
      ['Weekly', 'Monday', 'Tuesday'],
      ['Rotate', 'Day1', 'Day2'],
    ]) {
      const created = await (
        await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkwwPlan' } })
      ).json()
      await page.request.post(`${backend}/api/plan/update`, {
        data: { planId: created.planId, data: { Info: { Mode: mode, RotateDays: 2 } } },
      })
      await app.goto(`/plans?planId=${created.planId}`)
      await page.reload()
      const table = page.locator('.okww-plan-table')
      const number = table.locator('input[role="spinbutton"]').first()
      await expect(number).toHaveValue('1')
      const saved = page.waitForResponse(r => r.url().includes('/api/plan/update'))
      await number.fill('3')
      await number.press('Tab')
      expect((await (await saved).json()).code).toBe(200)
      await page.reload()
      await expect(number).toHaveValue('3')
      const result = (
        await (
          await page.request.post(`${backend}/api/plan/get`, { data: { planId: created.planId } })
        ).json()
      ).data[created.planId]
      expect(result[group].Key.WhichTacetSuppressionToFarm).toBe(3)
      expect(result[other].Key.WhichTacetSuppressionToFarm).toBe(1)
      await expect(
        table.getByRole('button', { name: 'Detailed configuration', exact: true })
      ).toHaveCount(0)
    }
  })
  test('irrelevant cells show a dash and preserve each farming choice', async ({ app, page }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkwwPlan' } })
    ).json()
    await app.goto(`/plans?planId=${created.planId}`)
    const row = page.locator('.okww-plan-table tr.ant-table-row').first()
    const cells = row.locator('td')
    await expect(cells.nth(3)).toHaveText('—')
    const chooseFarm = async (label: string) => {
      await row.locator('.ant-select').first().click()
      const saved = page.waitForResponse(r => r.url().includes('/api/plan/update'))
      await page.getByTitle(label, { exact: true }).click()
      expect((await (await saved).json()).code).toBe(200)
    }
    await chooseFarm('模拟领域')
    await expect(cells.nth(2)).toHaveText('—')
    await expect(cells.nth(2).locator('input')).toHaveCount(0)
    await cells.nth(3).locator('.ant-select').click()
    const saved = page.waitForResponse(r => r.url().includes('/api/plan/update'))
    await page.getByTitle('武器经验', { exact: true }).click()
    await saved
    await chooseFarm('凝素领域')
    await expect(cells.nth(3)).toHaveText('—')
    await expect(cells.nth(2).locator('input')).toHaveValue('1')
    await chooseFarm('模拟领域')
    await expect(cells.nth(3)).toContainText('武器经验')
    await page.reload()
    await expect(cells.nth(2)).toHaveText('—')
    await expect(cells.nth(3)).toContainText('武器经验')
    await expect(row.locator('.ant-select-borderless')).toHaveCount(4)
    await page.setViewportSize({ width: 1653, height: 1080 })
    await app.evidence('okww-plan-light')
    await app.goto('/settings')
    await page.locator('.theme-mode-control').getByText('Dark', { exact: true }).click()
    await app.goto(`/plans?planId=${created.planId}`)
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect(cells.nth(2)).toHaveText('—')
    await app.evidence('okww-plan-dark')
  })
  test('failed saves retain drafts and retry', async ({ app, page }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkwwPlan' } })
    ).json()
    await app.goto(`/plans?planId=${created.planId}`)
    const number = page.locator('.okww-plan-table input[role="spinbutton"]').first()
    await expect(number).toHaveValue('1')
    await page.route(
      '**/api/plan/update',
      route =>
        route.fulfill({
          status: 200,
          json: { code: 400, status: 'error', message: 'Injected save failure' },
        }),
      { times: 1 }
    )
    await number.fill('5')
    await number.press('Tab')
    await expect(number).toHaveValue('5')
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0)
    await page.reload()
    await expect(number).toHaveValue('5')
  })
})
