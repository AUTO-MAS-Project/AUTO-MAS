import type { APIRequestContext } from '@playwright/test'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
const post = async (request: APIRequestContext, path: string, data: unknown) => {
  const response = await request.post(`${backend}${path}`, { data })
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  expect(body.code).toBe(200)
  return body
}

test.describe('@maa-plan-display', () => {
  test('uses the plan name while options are delayed and after reopening', async ({
    app,
    page,
  }) => {
    const plan = await post(page.request, '/api/plan/add', { type: 'MaaPlan' })
    await post(page.request, '/api/plan/update', {
      planId: plan.planId,
      data: { Info: { Name: 'Plan display test', Mode: 'ALL' }, ALL: { Stage: '1-7' } },
    })
    const script = await post(page.request, '/api/scripts/add', { type: 'MAA' })
    const user = await post(page.request, '/api/scripts/user/add', { scriptId: script.scriptId })
    await post(page.request, '/api/scripts/user/update', {
      scriptId: script.scriptId,
      userId: user.userId,
      data: {
        Info: { Name: 'isolated', IfQuickConfig: true },
        Stage: { Stage: 'AP-5', StageMode: plan.planId },
        Task: { IfFight: true },
      },
    })
    let release!: () => void
    let releasePlan!: () => void
    const pending = new Promise<void>(resolve => {
      release = resolve
    })
    const pendingPlan = new Promise<void>(resolve => {
      releasePlan = resolve
    })
    await page.route('**/api/plan/get', async route => {
      if (route.request().postDataJSON()?.planId !== plan.planId) return route.continue()
      await pendingPlan
      await route.continue()
    })
    await page.route('**/api/info/combox/plan', async route => {
      await pending
      await route.continue()
    })
    await app.goto(`/scripts/${script.scriptId}/users/${user.userId}/edit/maa`)
    const row = page
      .locator('.task-row')
      .filter({ has: page.locator('.row-name', { hasText: 'Sanity tasks' }) })
    await row.locator('.row-main').first().click()
    await expect(row.locator('.ant-select-selection-item').first()).toHaveText(
      'Loading the configuration...'
    )
    await expect(row.locator('.ant-select-selection-item').first()).not.toContainText(plan.planId)
    releasePlan()
    await expect(row.locator('.row-summary')).toContainText('1-7')
    await expect(row.locator('.row-summary')).toContainText('Plan display test')
    await expect(row.locator('.row-summary')).not.toContainText(plan.planId)
    await expect(row.locator('.ant-select-selection-item').first()).toHaveText('Plan display test')
    await expect(row.locator('.plan-value').filter({ hasText: '1-7' })).toBeVisible()
    await app.evidence('maa-plan-display-name')
    release()
    await page.unroute('**/api/info/combox/plan')
    await page.unroute('**/api/plan/get')
    await page.reload()
    await expect(row.locator('.row-summary')).toContainText('Plan display test')
    await expect(row.locator('.row-summary')).toContainText('1-7')
    await expect(row.locator('.row-summary')).not.toContainText(plan.planId)
    await page.route('**/api/plan/get', async route => {
      if (route.request().postDataJSON()?.planId !== plan.planId) return route.continue()
      await route.fulfill({ status: 200, json: { code: 500, index: [], data: {} } })
    })
    await page.route('**/api/info/combox/plan', route =>
      route.fulfill({ status: 200, json: { code: 500, data: [] } })
    )
    await page.reload()
    await row.locator('.row-main').first().click()
    await expect(row.getByText(/Could not load the plan configuration/).first()).toBeVisible()
    await expect(row.locator('.ant-select-selection-item').first()).not.toContainText(plan.planId)
    await expect(row.locator('.plan-value')).toHaveCount(0)
  })
})
