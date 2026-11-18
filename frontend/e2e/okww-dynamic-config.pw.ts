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
      JSON.stringify({
        'New native limit': 17,
        'Teleport to Boss': 'Weekly Challenge',
        'Exit After Task': true,
        _hidden: true,
      })
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
    const repeatCount = page
      .locator('.ant-form-item')
      .filter({ has: page.locator('label').filter({ hasText: 'Repeat Farm Count' }) })
      .getByRole('spinbutton')
    await expect(repeatCount).toHaveValue('10000')
    await fs.writeFile(
      path.join(configs, 'FarmEchoTask.json'),
      JSON.stringify({
        'Repeat Farm Count': 99,
        'New native limit': 17,
        'Teleport to Boss': 'Weekly Challenge',
        'Exit After Task': true,
        _hidden: true,
      })
    )
    await page
      .locator('.config-mode-option')
      .filter({ has: page.locator('input[value="native"]') })
      .click()
    await expect(repeatCount).toHaveValue('99')
    await page
      .locator('.config-mode-option')
      .filter({ has: page.locator('input[value="shared"]') })
      .click()
    await expect(repeatCount).toHaveValue('10000')
    const echoLabels = page.locator('.ant-tabs-tabpane-active .native-config-field label')
    await expect(echoLabels.nth(2)).toHaveText('Which Weekly Boss to Teleport')
    await expect(echoLabels.nth(4)).toHaveText('Boss')
    await expect(
      page.locator('.ant-tabs-tabpane-active label').filter({ hasText: 'Exit After Task' })
    ).toHaveCount(0)
    await expect(page.getByText('_hidden', { exact: true })).not.toBeVisible()
    const saved = page.waitForResponse(
      r => r.url().endsWith('/api/scripts/okww/task-config') && r.request().method() === 'POST'
    )
    await page.route(
      '**/api/scripts/okww/task-config',
      async route => {
        // 延迟保存响应，验证等待期间不会整页变成骨架或遮罩。
        await new Promise(resolve => setTimeout(resolve, 500))
        await route.continue()
      },
      { times: 1 }
    )
    await input.fill('22')
    await input.press('Tab')
    await expect(input).toBeEnabled()
    await expect(page.locator('.ant-card-loading')).toHaveCount(0)
    await expect(page.locator('.ant-spin-blur')).toHaveCount(0)
    const latestSaved = page.waitForResponse(
      r =>
        r.url().endsWith('/api/scripts/okww/task-config') &&
        r.request().method() === 'POST' &&
        r.request().postDataJSON().values['New native limit'] === 23
    )
    await input.fill('23')
    await input.press('Tab')
    expect((await (await saved).json()).code).toBe(200)
    expect((await (await latestSaved).json()).code).toBe(200)
    // 一次成功、下一次失败：保留失败草稿和提示，不能被成功后的刷新吞掉。
    let writes = 0
    await page.route('**/api/scripts/okww/task-config', async route => {
      if (route.request().method() !== 'POST') return route.continue()
      writes++
      if (writes === 1) {
        await new Promise(resolve => setTimeout(resolve, 300))
        return route.continue()
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 400,
          status: 'error',
          message: 'Save rejected for regression test',
        }),
      })
    })
    const firstEdit = page.waitForResponse(
      r => r.url().endsWith('/api/scripts/okww/task-config') && r.request().method() === 'POST'
    )
    await input.fill('24')
    const rejected = page.waitForResponse(
      r =>
        r.url().endsWith('/api/scripts/okww/task-config') &&
        r.request().method() === 'POST' &&
        r.request().postDataJSON().values['New native limit'] === 25
    )
    await input.fill('25')
    await firstEdit
    await rejected
    await expect(page.getByText('Save rejected for regression test', { exact: true })).toBeVisible()
    await expect(input).toHaveValue('25')
    await page.unroute('**/api/scripts/okww/task-config')
    await page.reload()
    await page.getByRole('tab', { name: '4C Echo settings', exact: true }).click()
    await expect(input).toHaveValue('24')
    const restoredEdit = page.waitForResponse(
      r => r.url().endsWith('/api/scripts/okww/task-config') && r.request().method() === 'POST'
    )
    await input.fill('23')
    await restoredEdit
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
      data: {
        Info: { Mode: 'ALL', Name: 'Review plan' },
        ALL: { Key: { WhichToFarm: 'Forgery Challenge' } },
      },
    })
    await page.getByRole('tab', { name: 'Daily tasks', exact: true }).click()
    // 重新加载选项后，在同一页面切换计划，字段须立即更新。
    await page.reload()
    await page.locator('.universal-plan-select').click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('Review plan', { exact: true })
      .click()
    const planned = field('Which to Farm').getByRole('combobox')
    await expect(planned).toBeDisabled()
    const exit = field('Exit After Task').getByRole('switch')
    await expect(exit).toBeDisabled()
    await expect(exit).toBeChecked()
    await post('/api/scripts/user/update', {
      scriptId,
      userId,
      data: { Task: { IfCustomArguments: true } },
    })
    await page.reload()
    await expect(exit).toBeEnabled()
    await expect(exit).not.toBeChecked()
    // 面板已经落盘、父页面尚未回读时，参数保存不得覆盖面板新值。
    let releaseRead!: () => void
    const readGate = new Promise<void>(resolve => (releaseRead = resolve))
    let readStarted!: () => void
    const pendingRead = new Promise<void>(resolve => (readStarted = resolve))
    await page.route('**/api/scripts/user/get', async route => {
      readStarted()
      await readGate
      await route.continue()
    })
    await page.getByRole('tab', { name: '4C Echo settings', exact: true }).click()
    await saveAction(() => input.fill('31'))
    await pendingRead
    await page.getByRole('tab', { name: 'OK-WW launch arguments', exact: true }).click()
    const argumentsInput = page.locator('.ant-tabs-tabpane-active input').first()
    await argumentsInput.fill('-t DailyTask -e --debug')
    const argumentsSaved = page.waitForResponse(
      r => r.url().endsWith('/api/scripts/user/update') && r.request().method() === 'POST'
    )
    await argumentsInput.press('Tab')
    expect((await (await argumentsSaved).json()).code).toBe(200)
    const crossed = await post('/api/scripts/user/get', { scriptId, userId })
    expect(crossed.data[userId].Task.FarmEchoConfig['New native limit']).toBe(31)
    expect(crossed.data[userId].Task.CustomArguments).toBe('-t DailyTask -e --debug')
    releaseRead()
    await page.unroute('**/api/scripts/user/get')
    await page.reload()
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
    await expect(input).toHaveValue('31')
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
