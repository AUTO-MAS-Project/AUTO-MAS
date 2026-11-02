import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@maa-cultivate-time material estimate', () => {
  test('uses the daily budget, saves the monthly card per user, and handles unavailable estimates', async ({
    app,
    page,
  }) => {
    let sanity: number | null = 10_000
    let previewFailure = false
    let releasePreview: (() => void) | undefined
    let waitForPreview = false
    await page.route('**/api/scripts/maa/cultivate/operators', route =>
      route.fulfill({ json: { code: 200, data: [] } })
    )
    await page.route('**/api/scripts/maa/cultivate/preview', async route => {
      if (waitForPreview) {
        waitForPreview = false
        await new Promise<void>(resolve => {
          releasePreview = resolve
        })
      }
      await route.fulfill({
        json: {
          code: previewFailure ? 500 : 200,
          message: previewFailure ? 'Preview unavailable' : '',
          stages: [],
          demands: [],
          unobtainable: [],
          hasProgression: true,
          hasInventory: true,
          progressions: [],
          totalExpectedSanity: sanity,
        },
      })
    })
    await page.route('**/api/scripts/maa/cultivate/refresh', route =>
      route.fulfill({ json: { code: 200, status: 'success' } })
    )
    await page.route('**/api/scripts/maa/depot/items', route =>
      route.fulfill({ json: { code: 200, data: [] } })
    )
    await page.route('**/api/scripts/maa/depot/inventory', route =>
      route.fulfill({ json: { code: 200, data: [] } })
    )

    const script = await (
      await page.request.post(`${backend}/api/scripts/add`, { data: { type: 'MAA' } })
    ).json()
    expect(script.code).toBe(200)
    const users: string[] = []
    for (const name of ['Estimate account', 'Other estimate account']) {
      const user = await (
        await page.request.post(`${backend}/api/scripts/user/add`, {
          data: { scriptId: script.scriptId },
        })
      ).json()
      expect(user.code).toBe(200)
      users.push(user.userId)
      const saved = await page.request.post(`${backend}/api/scripts/user/update`, {
        data: {
          scriptId: script.scriptId,
          userId: user.userId,
          data: {
            Info: { Name: name },
            Task: {
              IfCultivate: true,
              CultivateTargets: JSON.stringify([
                { operator_id: 'operator', goals: [{ kind: 'elite', target_id: '', to_level: 1 }] },
              ]),
            },
          },
        },
      })
      expect((await saved.json()).code).toBe(200)
    }
    const visitUser = (index: number) =>
      app.goto(`/scripts/${script.scriptId}/users/${users[index]}/cultivate/maa`)
    const overview = page.locator('.cultivation-overview')
    const time = overview.locator('.material-time-stat .ant-statistic-content')
    const card = overview.getByRole('checkbox', { name: 'Monthly Card', exact: true })

    await visitUser(0)
    await expect(time).toHaveText('~32d')
    await expect(card).not.toBeChecked()
    await expect(
      overview.locator('.execution-checks').getByRole('checkbox', { name: 'Monthly Card' })
    ).toBeVisible()
    await expect(
      overview.locator('.execution-checks').getByRole('checkbox').first()
    ).toHaveAccessibleName('Monthly Card')
    await overview
      .getByRole('button', {
        name: 'Only used to estimate material days. Does not affect task execution.',
        exact: true,
      })
      .hover()
    await expect(page.getByRole('tooltip')).toContainText('Does not affect task execution.')
    await overview.getByText('Estimated material time', { exact: true }).hover()
    await expect(page.getByRole('tooltip')).toBeHidden()
    await expect(page.locator('.cultivate-preview')).not.toContainText('10,000')

    const savedCard = page.waitForResponse(
      response =>
        response.url().endsWith('/api/scripts/user/update') &&
        response.request().postDataJSON()?.data?.Task?.CultivateMonthlyCard === true
    )
    await card.check()
    expect((await (await savedCard).json()).code).toBe(200)
    await expect(time).toHaveText('~25d')
    await page.reload()
    await expect(card).toBeChecked()
    await expect(time).toHaveText('~25d')
    for (const width of [1280, 1024]) {
      await page.setViewportSize({ width, height: 900 })
      const bounds = await overview.boundingBox()
      const checks = overview.locator('.execution-checks')
      const group = await checks.boundingBox()
      const label = await checks.locator(':scope > *').last().boundingBox()
      expect(bounds).not.toBeNull()
      expect(group).not.toBeNull()
      expect(label).not.toBeNull()
      expect(label!.x + label!.width).toBeLessThanOrEqual(bounds!.x + bounds!.width)
      expect(Math.abs(label!.x + label!.width - group!.x - group!.width)).toBeLessThanOrEqual(1)
    }
    await page.setViewportSize({ width: 1280, height: 900 })
    await app.evidence('material-time-monthly-light')

    await visitUser(1)
    await expect(card).not.toBeChecked()
    await expect(time).toHaveText('~32d')
    await page.evaluate(async () => {
      const modulePath = '/src/composables/useTheme.ts'
      const { useTheme } = await import(modulePath)
      await useTheme().setThemeMode('dark')
    })
    await expect(page.locator('html')).toHaveClass(/dark/)
    await app.evidence('material-time-dark')

    const refresh = page.getByRole('button', { name: 'Refresh data', exact: true })
    sanity = 1
    waitForPreview = true
    await refresh.click()
    await expect(time).toHaveText('Computing')
    releasePreview?.()
    await expect(time).toHaveText('~1d')
    await expect(refresh).toBeEnabled()

    sanity = null
    await refresh.click()
    await expect(time).toHaveText('—')
    await expect(refresh).toBeEnabled()
    sanity = 0
    await refresh.click()
    await expect(time).toHaveText('No extra sanity needed')
    await expect(refresh).toBeEnabled()
    previewFailure = true
    await refresh.click()
    await expect(time).toHaveText('—')
    await expect(page.getByText('Preview unavailable', { exact: true }).first()).toBeVisible()

    await page.evaluate(async () => {
      const modulePath = '/src/composables/useLocale.ts'
      const { useLocale } = await import(modulePath)
      await useLocale().setLocale('zh-CN')
    })
    await expect(overview.getByRole('checkbox', { name: '月卡', exact: true })).toBeVisible()
    await overview
      .getByRole('button', { name: '仅用于预计材料天数，不影响任务执行。', exact: true })
      .hover()
    await expect(page.getByRole('tooltip')).toHaveText('仅用于预计材料天数，不影响任务执行。')
    await overview.locator('.material-time-stat button').hover()
    await expect(
      page.getByRole('tooltip').filter({ hasText: '按每日 288、每周 240' })
    ).toBeVisible()
    await app.evidence('material-time-chinese-hint')
  })
})
