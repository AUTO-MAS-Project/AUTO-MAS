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
      ).toHaveCount(mode === 'ALL' ? 1 : mode === 'Weekly' ? 7 : 2)
    }
  })
  test('detailed overrides share the quick table and can restore inheritance', async ({
    app,
    page,
  }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkwwPlan' } })
    ).json()
    await app.goto(`/plans?planId=${created.planId}`)
    const table = page.locator('.okww-plan-table')
    await table.getByRole('button', { name: 'Detailed configuration', exact: true }).first().click()
    const detail = page.locator('.okww-plan-detail')
    const number = detail.getByRole('spinbutton')
    await expect(number).toHaveValue('1')
    await page.setViewportSize({ width: 1440, height: 1000 })
    await expect(detail.locator('.ant-spin-container')).toHaveCSS('opacity', '1')
    await app.evidence('okww-plan-detail-light')
    const save = () =>
      page.waitForResponse(
        r => r.url().includes('/okww/plan/configs') && r.request().method() === 'POST'
      )
    let response = save()
    await number.fill('4')
    await number.press('Tab')
    expect((await (await response).json()).code).toBe(200)
    await detail.getByRole('button', { name: 'Back', exact: true }).click()
    await expect(table.getByRole('spinbutton').first()).toHaveValue('4')
    await table.getByRole('button', { name: 'Detailed configuration', exact: true }).first().click()
    await expect(number).toHaveValue('4')
    response = save()
    await detail.getByRole('button', { pressed: true }).click()
    expect((await (await response).json()).code).toBe(200)
    await detail.getByRole('button', { name: 'Back', exact: true }).click()
    await expect(table.locator('.ant-table-row').first().getByRole('spinbutton')).toHaveCount(0)
    await app.goto('/settings')
    await page.locator('.theme-mode-control').getByText('Dark', { exact: true }).click()
    await app.goto(`/plans?planId=${created.planId}`)
    await table.getByRole('button', { name: 'Detailed configuration', exact: true }).first().click()
    await expect(detail.getByRole('menuitem')).toHaveCount(6)
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect(detail.locator('.ant-spin-container')).toHaveCSS('opacity', '1')
    await app.evidence('okww-plan-detail-dark')
  })

  test('4C target is inherited or saved as a group', async ({ app, page }) => {
    const { planId } = await (
      await page.request.post(`${backend}/api/plan/add`, {
        data: { type: 'OkwwPlan' },
      })
    ).json()
    const url = `${backend}/api/scripts/okww/plan/configs`
    const partial = await (
      await page.request.post(url, {
        data: {
          plan_id: planId,
          day: 'Monday',
          configs: { 'FarmEchoTask.json': { Boss: 'Lorelei' } },
        },
      })
    ).json()
    expect(partial.code).toBe(400)
    await app.goto(`/plans/${planId}/okww/Monday`)
    const detail = page.locator('.okww-plan-detail')
    await detail.getByRole('menuitem', { name: '4C Echo settings', exact: true }).click()
    const field = (text: string) =>
      detail.locator('.ant-form-item').filter({ has: page.getByText(text, { exact: true }) })
    const group = field('Boss target').getByRole('button')
    await expect(field('Teleport to Boss')).toHaveCount(0)
    const saving = () =>
      page.waitForResponse(
        response => response.url() === url && response.request().method() === 'POST'
      )
    let saved = saving()
    await group.click()
    expect((await (await saved).json()).code).toBe(200)
    const teleport = field('Teleport to Boss')
    await expect(teleport.getByRole('button')).toHaveCount(0)
    await teleport.locator('.ant-select').click()
    saved = saving()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('Boss Challenge', { exact: true })
      .click()
    expect((await (await saved).json()).code).toBe(200)
    const read = async () =>
      (
        await (await page.request.get(url, { params: { plan_id: planId, day: 'Monday' } })).json()
      ).data.find((item: { kind: string }) => item.kind === 'echo').overrides
    expect(await read()).toMatchObject({
      'Teleport to Boss': 'Boss Challenge',
      'Which Boss Challenge to Teleport': 1,
      'Boss Level': '80',
      Boss: 'Other',
    })
    await app.evidence('okww-grouped-boss-target')
    saved = saving()
    await group.click()
    expect((await (await saved).json()).code).toBe(200)
    expect(await read()).toEqual({})
  })

  test('MAS switching requires game management while native modes remain available', async ({
    app,
    page,
  }) => {
    const { scriptId } = await (
      await page.request.post(`${backend}/api/scripts/add`, { data: { type: 'Okww' } })
    ).json()
    await app.goto(`/scripts/${scriptId}/edit/okww`)
    const message = 'Enable game configuration to switch accounts with MAS.'
    await expect(page.getByText(message, { exact: false })).toBeVisible()
    const row = page.locator('.game-control-row').filter({ hasText: 'MAS (recommended)' })
    await row.locator('.ant-select').last().click()
    const dropdown = page.locator('.ant-select-dropdown:visible')
    for (const label of [
      'MAS (recommended)',
      'ok-ww: one account per run',
      'ok-ww: batch switching',
    ]) {
      const option = dropdown.locator('.ant-select-item-option').filter({ hasText: label })
      if (label === 'MAS (recommended)') await expect(option).toHaveClass(/option-disabled/)
      else await expect(option).not.toHaveClass(/option-disabled/)
    }
    await page.keyboard.press('Escape')
    await app.evidence('okww-mas-switch-game-disabled')
    const update = await (
      await page.request.post(`${backend}/api/scripts/update`, {
        data: { scriptId, data: { Game: { Enabled: true } } },
      })
    ).json()
    expect(update.code).toBe(200)
    await page.reload()
    await expect(page.getByText(message, { exact: false })).toHaveCount(0)
    await row.locator('.ant-select').last().click()
    await expect(
      dropdown.locator('.ant-select-item-option').filter({ hasText: 'MAS (recommended)' })
    ).not.toHaveClass(/option-disabled/)
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
    await expect(row.locator('.ant-select-borderless')).toHaveCount(3)
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
    await expect(page.locator('.okww-plan-table input[role="spinbutton"]').nth(1)).toBeDisabled()
    await expect(page.locator('.additional-task-trigger').nth(1)).toBeDisabled()
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0)
    await page.reload()
    await expect(number).toHaveValue('5')
  })
  test('daily echo supports on, off and inheritance after reload', async ({ app, page }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkwwPlan' } })
    ).json()
    await app.goto(`/plans?planId=${created.planId}`)
    const selector = page
      .locator('.okww-plan-table tr.ant-table-row')
      .first()
      .locator('td')
      .nth(4)
      .locator('.ant-select')
    for (const [label, expected] of [
      ['On', true],
      ['Off', false],
      ['Inherit', null],
      ['On', true],
      ['Inherit', null],
    ] as const) {
      await selector.click()
      const saved = page.waitForResponse(r => r.url().includes('/api/plan/update'))
      await page.locator('.ant-select-dropdown:visible').getByTitle(label, { exact: true }).click()
      expect((await (await saved).json()).code).toBe(200)
      await page.reload()
      await expect(selector).toContainText(label)
      const result = (
        await (
          await page.request.post(`${backend}/api/plan/get`, { data: { planId: created.planId } })
        ).json()
      ).data[created.planId]
      expect(result.Monday.Key.FarmNightmareNestForDailyEcho).toBe(expected)
    }
  })
  test('additional task checklist stays open and separates inheritance from tasks', async ({
    app,
    page,
  }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkwwPlan' } })
    ).json()
    await app.goto(`/plans?planId=${created.planId}`)
    const trigger = page.locator('.additional-task-trigger').first()
    await expect(trigger).toContainText('Inherit')
    await expect(page.locator('.okww-plan-table').getByRole('checkbox')).toHaveCount(0)
    await trigger.click()
    const editor = page.locator('.ant-popover:visible .additional-task-editor')
    const garden = editor.getByRole('checkbox', { name: '检查每周乐园', exact: true })
    const nest = editor.getByRole('checkbox', { name: '自动刷所有梦魇巢穴', exact: true })
    await expect(editor.getByRole('checkbox')).toHaveCount(4)
    await garden.check()
    await nest.check()
    const read = async () =>
      (
        await (
          await page.request.post(`${backend}/api/plan/get`, { data: { planId: created.planId } })
        ).json()
      ).data[created.planId].Monday.Key.AdditionalTasks
    await expect.poll(read).toEqual(['Check Weekly Garden', 'Auto Farm all Nightmare Nest'])
    await expect(trigger).toContainText('Weekly Garden')
    await expect(trigger).toContainText('All Nightmare Nests')
    await expect(
      page.getByRole('spinbutton', { name: 'Mon Dungeon number (F2)', exact: true })
    ).toBeVisible()
    await garden.uncheck()
    await nest.uncheck()
    await expect.poll(read).toEqual([])
    await expect(trigger).toContainText('Off')
    await editor.getByRole('button', { name: 'Inherit', exact: true }).click()
    await expect.poll(read).toBeNull()
    await page.reload()
    await expect(trigger).toContainText('Inherit')
    await page.setViewportSize({ width: 1653, height: 1080 })
    await app.evidence('okww-additional-compact')
    await trigger.click()
    await expect(editor).toBeVisible()
    await page
      .locator('.ant-popover:visible')
      .evaluate(element =>
        Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished))
      )
    await app.evidence('okww-additional-checklist')
    await app.goto(`/plans/${created.planId}/okww/Monday`)
    const detail = page.locator('.okww-plan-detail')
    const tasks = detail.locator('.override-item').filter({
      has: page.getByText('Additional Tasks to Run After Daily Task', { exact: true }),
    })
    await expect(tasks.getByRole('checkbox')).toHaveCount(0)
    await tasks.getByRole('button', { pressed: false }).click()
    await expect(tasks.getByRole('checkbox')).toHaveCount(4)
    await tasks.getByRole('checkbox', { name: 'Check Weekly Garden', exact: true }).uncheck()
    await expect.poll(read).toEqual([])
    await tasks.getByRole('checkbox', { name: 'Teleport and Farm 4C Echo', exact: true }).check()
    await expect.poll(read).toEqual(['Teleport and Farm 4C Echo'])
    await page.reload()
    await expect(
      tasks.getByRole('checkbox', { name: 'Teleport and Farm 4C Echo', exact: true })
    ).toBeChecked()
    await expect(detail.locator('.ant-spin-container')).toHaveCSS('opacity', '1')
    await app.evidence('okww-additional-detail-checkboxes')
  })
})

test.describe('@plan-save-recovery', () => {
  for (const adapter of [
    { type: 'OkwwPlan', route: 'okww', endpoint: 'configs' },
    { type: 'OkNtePlan', route: 'oknte', endpoint: 'save' },
  ]) {
    test(`${adapter.type} can discard details after a persistent save error`, async ({
      app,
      page,
    }) => {
      const created = await (
        await page.request.post(`${backend}/api/plan/add`, { data: { type: adapter.type } })
      ).json()
      await app.goto(`/plans/${created.planId}/${adapter.route}/Monday`)
      await page.route(`**/${adapter.route}/plan/${adapter.endpoint}`, route =>
        route.request().method() !== 'POST'
          ? route.continue()
          : route.fulfill({ json: { code: 400, status: 'error', message: 'Plan save rejected' } })
      )
      const edit = page.locator('.override-editor')
      await edit.getByRole('button', { pressed: false }).first().click()
      await expect(edit.getByText('Plan save rejected', { exact: false })).toBeVisible()
      await expect(edit.getByRole('button', { pressed: true }).first()).toBeEnabled()
      await page.getByRole('button', { name: 'Back', exact: true }).click()
      await expect(edit).toBeVisible()
      await edit.getByRole('button', { name: 'Discard and return', exact: true }).click()
      await expect(page).toHaveURL(new RegExp(`/plans\\?planId=${created.planId}$`))
      await expect(edit).toHaveCount(0)
    })
  }
})
