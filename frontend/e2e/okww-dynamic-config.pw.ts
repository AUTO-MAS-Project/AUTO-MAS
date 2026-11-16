import fs from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './fixtures'
const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
test.describe('@okww-dynamic-config', () => {
  test('edits an unknown native field and preserves it after reload', async ({
    app,
    page,
  }, testInfo) => {
    async function post(endpoint: string, data: unknown) {
      const response = await page.request.post(`${backend}${endpoint}`, { data })
      const body = await response.json()
      expect(body.code, body.message).toBe(200)
      return body
    }
    const install = testInfo.outputPath('okww-install')
    const appDir = path.join(install, 'data/apps/ok-ww')
    const configs = path.join(appDir, 'working/configs')
    await fs.mkdir(configs, { recursive: true })
    await fs.writeFile(path.join(install, 'ok-ww.exe'), '')
    await fs.writeFile(path.join(appDir, 'app.json'), '{"current_version":"v3.8.0"}')
    await fs.writeFile(path.join(configs, 'DailyTask.json'), '{}')
    await fs.writeFile(
      path.join(configs, 'FarmEchoTask.json'),
      JSON.stringify({ 'New native limit': 17, 'Exit After Task': true, _hidden: true })
    )
    const { scriptId } = await post('/api/scripts/add', { type: 'Okww' })
    await post('/api/scripts/update', { scriptId, data: { Info: { RootPath: install } } })
    const { userId } = await post('/api/scripts/user/add', { scriptId })
    await app.goto(`/scripts/${scriptId}/users/${userId}/edit/okww`)
    await page.getByRole('tab', { name: '4C Echo settings', exact: true }).click()
    const item = page
      .locator('.ant-form-item')
      .filter({ has: page.locator('label').filter({ hasText: 'New native limit' }) })
    const input = item.getByRole('spinbutton')
    await expect(input).toHaveValue('17')
    await expect(
      page.locator('.ant-tabs-tabpane-active label').filter({ hasText: 'Exit After Task' })
    ).toHaveCount(0)
    await expect(page.getByText('_hidden', { exact: true })).not.toBeVisible()
    const saved = page.waitForResponse(
      r => r.url().endsWith('/api/scripts/okww/task-config') && r.request().method() === 'POST'
    )
    await input.fill('23')
    await input.press('Tab')
    expect((await (await saved).json()).code).toBe(200)
    await page.reload()
    await page.getByRole('tab', { name: '4C Echo settings', exact: true }).click()
    await expect(input).toHaveValue('23')
    await expect(input).toBeEnabled()
    await expect(page.locator('.ant-spin-blur')).toHaveCount(0)
    await app.evidence('okww-dynamic-new-field')
    await app.goto('/settings')
    await page.locator('.theme-mode-control').getByText('Dark', { exact: true }).click()
    await app.goto(`/scripts/${scriptId}/users/${userId}/edit/okww`)
    await page.getByRole('tab', { name: '4C Echo settings', exact: true }).click()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect(input).toHaveValue('23')
    await expect(input).toBeEnabled()
    await expect(page.locator('.ant-spin-blur')).toHaveCount(0)
    await app.evidence('okww-dynamic-dark')
    await page.getByRole('tab', { name: 'Daily tasks', exact: true }).click()
    const checks = page.locator('.native-checkboxes')
    await expect(checks.getByRole('checkbox')).toHaveCount(4)
    const echoCheck = checks.getByRole('checkbox', {
      name: 'Teleport and Farm 4C Echo',
      exact: true,
    })
    await expect(echoCheck).toBeEnabled()
    const dailySaved = page.waitForResponse(
      r => r.url().endsWith('/api/scripts/okww/task-config') && r.request().method() === 'POST'
    )
    await echoCheck.check()
    expect((await (await dailySaved).json()).code).toBe(200)
    await page.reload()
    await expect(echoCheck).toBeChecked()
    await expect(echoCheck).toBeEnabled()
    await expect(page.locator('.ant-spin-blur')).toHaveCount(0)
    await checks.scrollIntoViewIfNeeded()
    await app.evidence('okww-daily-checkboxes')
    await page.getByRole('tab', { name: '4C Echo settings', exact: true }).click()
    async function saveAction(action: () => Promise<void>) {
      const response = page.waitForResponse(
        r => r.url().endsWith('/api/scripts/okww/task-config') && r.request().method() === 'POST'
      )
      await action()
      expect((await (await response).json()).code).toBe(200)
    }
    const field = (name: string) =>
      page
        .locator('.ant-form-item')
        .filter({ has: page.locator('label').filter({ hasText: name }) })
    await page.getByRole('tab', { name: 'Nightmare targets', exact: true }).click()
    const nest = page.getByRole('checkbox', { name: 'Tacet Discord Nest', exact: true })
    await expect(nest).toBeChecked()
    await saveAction(() => nest.uncheck())
    await expect(nest).toBeEnabled()
    await page.getByRole('tab', { name: 'Character settings', exact: true }).click()
    const c6 = field('Iuno C6').getByRole('switch')
    await expect(c6).toBeEnabled()
    await saveAction(() => c6.click())
    await expect(c6).toBeChecked()
    await page.getByRole('tab', { name: 'Monthly card', exact: true }).click()
    const time = field('Monthly Card Time').getByRole('spinbutton')
    await expect(page.locator('.ant-tabs-tabpane-active')).toContainText(
      'Does not detect ownership'
    )
    await expect(time).toHaveValue('4')
    await saveAction(() => time.fill('8'))
    await expect(time).toBeEnabled()
    await page.getByRole('tab', { name: 'Combat settings', exact: true }).click()
    const healer = field('Switch to Healer before and after Combat').getByRole('switch')
    await expect(healer).toBeEnabled()
    await saveAction(() => healer.click())
    const { planId } = await post('/api/plan/add', { type: 'OkwwPlan' })
    await post('/api/plan/update', {
      planId,
      data: { Info: { Mode: 'ALL' }, ALL: { Key: { WhichToFarm: 'Forgery Challenge' } } },
    })
    await post('/api/scripts/user/update', {
      scriptId,
      userId,
      data: { Info: { PlanMode: planId } },
    })
    await page.reload()
    const planned = field('Which to Farm').getByRole('combobox')
    await expect(planned).toBeDisabled()
    const exit = field('Exit After Task').getByRole('switch')
    await expect(exit).toBeEnabled()
    const accountWrite = page.waitForRequest(
      r => r.url().endsWith('/api/scripts/okww/task-config') && r.method() === 'POST'
    )
    await saveAction(() => exit.click())
    expect((await accountWrite).postDataJSON().values).not.toHaveProperty('Which to Farm')
    await expect(exit).toBeChecked()
    const info = await post('/api/scripts/user/get', { scriptId, userId })
    expect(info.data[userId].Task.WhichToFarm).toBe('Tacet Suppression')
    expect(info.data[userId].Task.FarmEchoConfig['Exit After Task']).toBe(true)
    const advanced = info.data[userId].Task.NativeConfigs
    expect(advanced['NightmareNestTask.json']['Which to Farm']).toEqual(['Nightmare Purification'])
    expect(advanced['Character Config.json']['Iuno C6']).toBe(true)
    expect(advanced['Monthly Card Config.json']['Monthly Card Time']).toBe(8)
    expect(advanced['AutoCombatTask.json']['Switch to Healer before and after Combat']).toBe(false)
    await expect(exit).toBeEnabled()
    await expect(page.locator('.ant-spin-blur')).toHaveCount(0)
    await exit.scrollIntoViewIfNeeded()
    await app.evidence('okww-plan-unmanaged-fields')
    await page.getByRole('tab', { name: '4C Echo settings', exact: true }).click()
    await page.setViewportSize({ width: 760, height: 900 })
    await expect(input).toBeVisible()
    await input.scrollIntoViewIfNeeded()
    await expect(page.locator('.ant-spin-blur')).toHaveCount(0)
    const width = await page
      .locator('.native-config-shell')
      .last()
      .evaluate(element => element.getBoundingClientRect().width)
    expect((await input.boundingBox())!.width).toBeGreaterThan(width * 0.8)
    await app.evidence('okww-dynamic-narrow')
  })
})
