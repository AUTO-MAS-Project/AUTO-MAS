import { expect, test } from './fixtures'
const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.use({
  video: 'off',
  launchOptions: { executablePath: process.env.AUTO_MAS_E2E_CHROMIUM_PATH },
})

test.describe('@universal-plan', () => {
  test('creates a script-level plan and enables it from user configuration', async ({
    app,
    page,
  }) => {
    const post = async (path: string, data: unknown) => {
      const response = await page.request.post(`${backend}${path}`, { data })
      const body = await response.json()
      expect(body.code).toBe(200)
      return body
    }
    const script = await post('/api/scripts/add', { type: 'General' })
    await post('/api/scripts/update', {
      scriptId: script.scriptId,
      data: { Info: { Name: 'Shared script' } },
    })
    const user = await post('/api/scripts/user/add', { scriptId: script.scriptId })
    await app.goto('/plans')
    await page.locator('.header-actions .ant-dropdown-trigger').click()
    await page
      .getByRole('menuitem')
      .filter({ hasText: /universal plan/i })
      .click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.locator('.ant-select').click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('Shared script', { exact: true })
      .click()
    await expect(dialog.getByRole('button', { name: 'OK', exact: true })).toBeEnabled()
    await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0)
    await app.evidence('universal-plan-create-script')
    await dialog.getByRole('button', { name: 'OK', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    await expect(page.getByText('Daily reset', { exact: true })).toBeVisible()
    const plans = await post('/api/plan/get', {})
    const plan = plans.index.find((item: { type: string }) => item.type === 'UniversalPlanConfig')
    expect(plan).toBeTruthy()
    expect(plans.data[plan.uid].Info.ScriptId).toBe(script.scriptId)
    expect(plans.data[plan.uid].Info.UserId).toBeUndefined()
    await app.goto(`/scripts/${script.scriptId}/users/${user.userId}/edit/general`)
    const toggle = page.getByRole('switch', { name: 'Enable universal plan', exact: true })
    await expect(toggle).not.toBeChecked()
    await toggle.click()
    await expect(toggle).toBeChecked()
    await expect(page.getByRole('button', { name: 'Edit plan', exact: true })).toBeVisible()
    await expect(toggle).toBeEnabled()
    await app.evidence('universal-plan-enabled-user')
    await page.reload()
    await expect(toggle).toBeChecked()
    await page.getByRole('button', { name: 'Edit plan', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`planId=${plan.uid}`))
    await expect(page.getByText('Daily reset', { exact: true })).toBeVisible()
    await app.evidence('universal-plan-table')
    await app.goto(`/scripts/${script.scriptId}/users/${user.userId}/edit/general`)
    await toggle.click()
    await expect(toggle).not.toBeChecked()
    await expect(toggle).toBeEnabled()
    await page.reload()
    await expect(toggle).not.toBeChecked()
    await toggle.click()
    await expect(toggle).toBeChecked()
    await expect(toggle).toBeEnabled()
    await app.goto('/settings')
    await page.locator('.appearance-select').click()
    await page.locator('.ant-select-dropdown:visible').getByText('Dark', { exact: true }).click()
    await app.goto(`/scripts/${script.scriptId}/users/${user.userId}/edit/general`)
    await expect(toggle).toBeChecked()
    await expect(toggle).toBeEnabled()
    await expect(toggle).toHaveClass(/ant-switch-checked/)
    await expect
      .poll(async () => {
        const control = await toggle.boundingBox()
        const handle = await toggle.locator('.ant-switch-handle').boundingBox()
        return Boolean(control && handle && handle.x > control.x + control.width / 2)
      })
      .toBe(true)
    await app.evidence('universal-plan-enabled-dark')
  })
})
