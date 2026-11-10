import { expect, test } from './fixtures'
const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
test.use({
  video: 'off',
  launchOptions: { executablePath: process.env.AUTO_MAS_E2E_CHROMIUM_PATH },
})
test.describe('@oknte-plan', () => {
  test('dynamic fields expand only when overridden', async ({ app, page }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkNtePlan' } })
    ).json()
    const read = async () =>
      (
        await (
          await page.request.post(`${backend}/api/plan/get`, { data: { planId: created.planId } })
        ).json()
      ).data[created.planId].Monday.Key.Configs
    const before = await read()
    await page.route('**/oknte/plan/configs?**', async route => {
      const url = new URL(route.request().url())
      const response = await route.fetch({ url: url.toString() })
      const body = await response.json()
      body.data
        .find((file: { filename: string }) => file.filename === 'DailyRoutineTaskConfigs.json')
        .fields.push({
          name: 'future',
          label: 'Future group',
          type: 'object',
          children: [
            { name: 'toggle', label: 'Future toggle', type: 'bool', value: true },
            { name: 'values', label: 'Future values', type: 'list', value: [1, 2] },
          ],
        })
      await route.fulfill({ response, json: body })
    })
    await app.goto(`/plans/${created.planId}/oknte/Monday`)
    await expect(page.locator('.override-editor > .ant-form')).toHaveCount(0)
    await page.locator('.config-item').getByText('日常子任务配置', { exact: true }).click()
    const row = page
      .locator('.ant-form-item')
      .filter({ has: page.getByText('Future group / Future toggle', { exact: true }) })
    await expect(row).toContainText('Inherit account configuration')
    await expect(
      row.getByRole('button', { name: 'Inherit account configuration', exact: true })
    ).toHaveAttribute('aria-pressed', 'false')
    const inheritedHeight = (await row.boundingBox())!.height
    expect(inheritedHeight).toBeLessThan(64)
    expect(await read()).toEqual(before)
    const saved = page.waitForResponse(response => response.url().includes('/oknte/plan/save'))
    await row.getByRole('button', { name: 'Inherit account configuration', exact: true }).click()
    await saved
    await expect(row.getByRole('switch')).toBeChecked()
    expect((await row.boundingBox())!.height).toBeGreaterThan(inheritedHeight)
    await expect(row.getByRole('button', { name: 'Daily override', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    const after = await read()
    expect(after['DailyRoutineTaskConfigs.json'].future).toEqual({ toggle: true })
    const values = page
      .locator('.ant-form-item')
      .filter({ has: page.getByText('Future group / Future values', { exact: true }) })
    await values.getByRole('button', { name: 'Inherit account configuration', exact: true }).click()
    await expect(values.locator('textarea')).toHaveValue('[\n  1,\n  2\n]')
    const reset = page.waitForResponse(response => response.url().includes('/oknte/plan/save'))
    await row.getByRole('button', { name: 'Daily override', exact: true }).click()
    await reset
    expect((await read())['DailyRoutineTaskConfigs.json'].future).toEqual({ values: [1, 2] })
  })

  test('quick table preserves disabled and inherited task states and uses server options', async ({
    app,
    page,
  }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkNtePlan' } })
    ).json()
    const patch = async (items: { id: string; enabled: boolean }[]) => {
      const saved = await (
        await page.request.post(`${backend}/api/scripts/oknte/plan/save`, {
          data: {
            plan_id: created.planId,
            day: 'Monday',
            replace: true,
            configs: { 'DailyRoutineTask.json': { 'Routine Items': items } },
          },
        })
      ).json()
      expect(saved.code).toBe(200)
      await app.goto(`/plans?planId=${created.planId}`)
      await page.reload()
    }
    const task = page.locator('[data-row-key=Monday] .ant-select').first()
    const selection = page.locator('.ant-table-tbody .ant-select').first()
    await patch([
      { id: 'daily_anomaly', enabled: false },
      { id: 'daily_anomaly_hunter', enabled: false },
    ])
    await expect(selection).toContainText('Off')
    await expect(page.locator('[data-row-key=Monday] .not-applicable')).toHaveCount(5)
    await patch([{ id: 'daily_anomaly', enabled: false }])
    await expect(selection).toContainText('Detailed configuration')
    await patch([])
    await expect(selection).toContainText('Inherit')
    await page.route('**/oknte/plan/configs?**', async route => {
      const response = await route.fetch()
      const body = await response.json()
      const fields = body.data.find(
        (file: { filename: string }) => file.filename === 'DailyRoutineTaskConfigs.json'
      ).fields
      fields
        .find((field: { name: string }) => field.name === 'daily_anomaly_hunter')
        .children.find((field: { name: string }) => field.name === '追猎目标')
        .options.push('E2E server target')
      await route.fulfill({ response, json: body })
    })
    await patch([{ id: 'daily_anomaly_hunter', enabled: true }])
    await task.isVisible()
    await page.locator('[data-row-key=Monday] .ant-select').last().click()
    await expect(page.locator('.ant-select-dropdown:visible')).toContainText('E2E server target')
  })

  test('detail load failure permits leaving and retrying', async ({ app, page }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkNtePlan' } })
    ).json()
    const pattern = '**/oknte/plan/configs?**'
    await page.route(pattern, route =>
      route.fulfill({ json: { code: 500, message: 'E2E load failure' } })
    )
    await app.goto(`/plans/${created.planId}/oknte/Monday`)
    await expect(page.getByText('Error: E2E load failure', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await expect(page).toHaveURL(/#\/plans\?planId=/)
    await app.goto(`/plans/${created.planId}/oknte/Monday`)
    await expect(page.getByText('Error: E2E load failure', { exact: true })).toBeVisible()
    await page.unroute(pattern)
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(page.getByText('Error: E2E load failure', { exact: true })).toHaveCount(0)
    await expect(page.locator('.configuration-scroll .ant-form-item').first()).toBeVisible()
  })

  test('quick and detailed daily configuration edit the same day', async ({ app, page }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkNtePlan' } })
    ).json()
    expect(created.code).toBe(200)
    await app.goto(`/plans?planId=${created.planId}`)
    await page.reload()
    const stamina = page.locator('.ant-table-tbody input[role=spinbutton]').first()
    await expect(stamina).toHaveValue('180')
    const quickSave = page.waitForResponse(r => r.url().includes('/api/plan/update'))
    await stamina.fill('120')
    await stamina.press('Tab')
    await quickSave
    await page.getByRole('button', { name: 'Detailed configuration', exact: true }).first().click()
    await expect(page).toHaveURL(/oknte\/Monday/)
    const navigationTitle = await page.locator('.override-editor .group-header').boundingBox()
    const formTitle = await page.locator('.configuration-panel h3').boundingBox()
    expect(Math.abs(navigationTitle!.y - formTitle!.y)).toBeLessThanOrEqual(1)
    await expect(page.getByRole('button', { name: 'Back', exact: true })).toHaveCSS(
      'height',
      '40px'
    )
    const coffeeRow = page
      .locator('.ant-form-item')
      .filter({ has: page.getByText('一咖舍', { exact: true }) })
    await expect(coffeeRow).toContainText('Inherit account configuration')
    const offSave = page.waitForResponse(response => response.url().includes('/oknte/plan/save'))
    await coffeeRow
      .getByRole('button', { name: 'Inherit account configuration', exact: true })
      .click()
    await offSave
    const readPlan = async () =>
      (
        await (
          await page.request.post(`${backend}/api/plan/get`, { data: { planId: created.planId } })
        ).json()
      ).data[created.planId]
    let current = await readPlan()
    expect(
      current.Monday.Key.Configs['DailyRoutineTask.json']['Routine Items'].find(
        (item: { id: string }) => item.id === 'coffee'
      ).enabled
    ).toBe(false)
    const inheritSave = page.waitForResponse(response =>
      response.url().includes('/oknte/plan/save')
    )
    await coffeeRow.getByRole('button', { name: 'Daily override', exact: true }).click()
    await inheritSave
    current = await readPlan()
    expect(
      current.Monday.Key.Configs['DailyRoutineTask.json']['Routine Items'].some(
        (item: { id: string }) => item.id === 'coffee'
      )
    ).toBe(false)
    await app.evidence('oknte-plan-inheritance')

    await page.locator('.config-item').getByText('日常子任务配置', { exact: true }).click()
    const configurationScroll = page.locator('.configuration-scroll')
    for (const height of [600, 720, 1080]) {
      await page.setViewportSize({ width: 1280, height })
      await configurationScroll.hover()
      await page.mouse.wheel(0, 1800)
      await expect
        .poll(() => configurationScroll.evaluate(element => element.scrollTop))
        .toBeGreaterThan(0)
      await expect(page.getByRole('button', { name: 'Back', exact: true })).toBeInViewport()
      await expect(
        page.locator('.config-item').getByText('日常子任务配置', { exact: true })
      ).toBeInViewport()
      await expect
        .poll(() => page.locator('.content-area').evaluate(element => element.scrollTop))
        .toBe(0)
      const bounds = await configurationScroll.boundingBox()
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(height)
    }
    await configurationScroll.evaluate(element => element.scrollTo({ top: 0 }))
    const detailed = page.getByRole('spinbutton').first()
    await expect(detailed).toHaveValue('120')
    const detailCard = page.locator('.oknte-plan-detail .config-card')
    await expect(detailCard).toBeVisible()
    await page.evaluate(() =>
      document.documentElement.classList.add('appearance-background-custom')
    )
    expect(
      await detailCard.evaluate(element => getComputedStyle(element).backgroundColor)
    ).not.toBe('rgba(0, 0, 0, 0)')
    await app.evidence('oknte-plan-detail-light')
    const detailSave = page.waitForResponse(r => r.url().includes('/oknte/plan/save'))
    await detailed.fill('90')
    await detailed.press('Tab')
    await detailSave
    await expect(detailed).toHaveValue('90')
    const staminaRow = page
      .locator('.ant-form-item')
      .filter({ has: page.getByText('异象界域 / 目标消耗体力', { exact: true }) })
    const resetSave = page.waitForResponse(response => response.url().includes('/oknte/plan/save'))
    await staminaRow.getByRole('button', { name: 'Daily override', exact: true }).click()
    await resetSave
    await expect(
      staminaRow.getByRole('button', { name: 'Inherit account configuration', exact: true })
    ).toBeVisible()
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await expect(stamina).toHaveValue('')
    await expect(page.locator('[data-row-key=Tuesday] input[role=spinbutton]').first()).toHaveValue(
      '180'
    )
    for (const width of [1280, 1653]) {
      await page.setViewportSize({ width, height: 1080 })
      const hunter = await page
        .getByRole('columnheader', { name: '追猎目标', exact: true })
        .boundingBox()
      const detail = await page
        .getByRole('columnheader', { name: 'Detailed configuration', exact: true })
        .boundingBox()
      expect(hunter).not.toBeNull()
      expect(detail).not.toBeNull()
      expect(detail!.x).toBeGreaterThanOrEqual(hunter!.x + hunter!.width - 1)
    }
    await app.evidence('oknte-quick-plan')
    await app.goto('/settings')
    await page.locator('.theme-mode-control').getByText('Dark', { exact: true }).click()
    await app.goto(`/plans?planId=${created.planId}`)
    await page.reload()
    await expect(stamina).toHaveValue('')
    await app.evidence('oknte-quick-plan-dark')
    await page.getByRole('button', { name: 'Detailed configuration', exact: true }).first().click()
    await page.locator('.config-item').getByText('日常子任务配置', { exact: true }).click()
    await expect(detailCard).toBeVisible()
    expect(
      await detailCard.evaluate(element => getComputedStyle(element).backgroundColor)
    ).not.toBe('rgba(0, 0, 0, 0)')
    await app.evidence('oknte-plan-detail-dark')
  })
  test('material edits stay sparse and failed detail saves can be retried', async ({
    app,
    page,
  }) => {
    const created = await (
      await page.request.post(`${backend}/api/plan/add`, { data: { type: 'OkNtePlan' } })
    ).json()
    const read = async () =>
      (
        await (
          await page.request.post(`${backend}/api/plan/get`, {
            data: { planId: created.planId },
          })
        ).json()
      ).data[created.planId].Monday.Key.Configs
    await page.request.post(`${backend}/api/scripts/oknte/plan/save`, {
      data: {
        plan_id: created.planId,
        day: 'Monday',
        replace: true,
        configs: {
          'DailyRoutineTask.json': { 'Routine Items': [{ id: 'daily_anomaly', enabled: true }] },
          'DailyRoutineTaskConfigs.json': {
            daily_anomaly: { 任务类型: '异能升级材料', 弧盘材料序号: 3 },
          },
        },
      },
    })
    await app.goto(`/plans?planId=${created.planId}`)
    const material = page.locator('[data-row-key=Monday] td').nth(5).getByRole('spinbutton')
    const saved = page.waitForResponse(r => r.url().includes('/api/plan/update'))
    await material.fill('2')
    await material.press('Tab')
    await saved
    const task = (await read())['DailyRoutineTaskConfigs.json'].daily_anomaly
    expect(task['异能材料序号']).toBe(2)
    expect(task['弧盘材料序号']).toBe(3)
    expect(task).not.toHaveProperty('空幕序号')
    await app.goto(`/plans/${created.planId}/oknte/Monday`)
    await page.route('**/oknte/plan/save', route =>
      route.fulfill({
        json: { code: 400, status: 'error', message: 'Temporary save failure' },
      })
    )
    const row = page
      .locator('.ant-form-item')
      .filter({ has: page.getByText('一咖舍', { exact: true }) })
    await row.getByRole('button', { name: 'Inherit account configuration', exact: true }).click()
    await expect(page.getByText('Error: Temporary save failure', { exact: true })).toBeVisible()
    await page.unroute('**/oknte/plan/save')
    const retried = page.waitForResponse(r => r.url().includes('/oknte/plan/save'))
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    await retried
    await expect(page.getByText('Error: Temporary save failure', { exact: true })).toHaveCount(0)
    expect((await read())['DailyRoutineTask.json']['Routine Items']).toContainEqual({
      id: 'coffee',
      enabled: false,
    })
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await expect(page).toHaveURL(/\/plans\?planId=/)
  })
})
