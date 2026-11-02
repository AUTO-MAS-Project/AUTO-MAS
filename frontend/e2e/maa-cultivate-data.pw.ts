import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@maa-cultivate-data manual refresh', () => {
  test('reloads the catalog and preview, keeps existing data on failure, and prevents duplicate clicks', async ({
    app,
    page,
  }) => {
    let version = 0
    let failureCode = 0
    let failCatalog = false
    let refreshRequests = 0
    let catalogRequests = 0
    let previewRequests = 0
    let complete: (() => void) | undefined
    await page.route('**/api/scripts/maa/cultivate/refresh', async route => {
      refreshRequests++
      if (refreshRequests === 1)
        await new Promise<void>(resolve => {
          complete = resolve
        })
      if (failureCode === -1) return route.abort('failed')
      if (!failureCode) version++
      await route.fulfill({
        json: { code: failureCode || 200, status: failureCode ? 'error' : 'success' },
      })
    })
    await page.route('**/api/scripts/maa/cultivate/operators', route => {
      catalogRequests++
      return route.fulfill({
        json: {
          code: failCatalog ? 500 : 200,
          data: [
            {
              value: 'operator',
              label: version ? 'Updated operator' : 'Existing operator',
              rarity: 6,
              profession: 'WARRIOR',
              maxElite: 2,
              maxSkillLevel: 7,
              dataMissing: false,
              skills: [],
              modules: [],
            },
          ],
        },
      })
    })
    await page.route('**/api/scripts/maa/cultivate/preview', route => {
      previewRequests++
      return route.fulfill({
        json: {
          code: 200,
          stages: [],
          demands: [],
          unobtainable: [],
          hasProgression: false,
          progressions: [],
        },
      })
    })
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
    const user = await (
      await page.request.post(`${backend}/api/scripts/user/add`, {
        data: { scriptId: script.scriptId },
      })
    ).json()
    expect(user.code).toBe(200)
    const saved = await page.request.post(`${backend}/api/scripts/user/update`, {
      data: {
        scriptId: script.scriptId,
        userId: user.userId,
        data: {
          Info: { Name: 'isolated cultivation refresh' },
          Task: {
            CultivateTargets: JSON.stringify([
              { operator_id: 'operator', goals: [{ kind: 'elite', target_id: '', to_level: 1 }] },
            ]),
          },
        },
      },
    })
    expect((await saved.json()).code).toBe(200)
    await app.goto(`/scripts/${script.scriptId}/users/${user.userId}/cultivate/maa`)
    const root = page.locator('.cultivation-page')
    const refresh = page.getByRole('button', { name: 'Refresh data', exact: true })
    await expect(root.getByText('Existing operator', { exact: true }).first()).toBeVisible()
    await expect(refresh).toBeEnabled()
    const beforeCatalog = catalogRequests
    const beforePreview = previewRequests
    await refresh.click()
    await expect(refresh).toBeDisabled()
    await expect.poll(() => refreshRequests).toBe(1)
    complete?.()
    await expect(
      page.getByText('Development data and operator catalog refreshed', { exact: true })
    ).toBeVisible()
    await expect(root.getByText('Updated operator', { exact: true }).first()).toBeVisible()
    expect(catalogRequests).toBeGreaterThan(beforeCatalog)
    expect(previewRequests).toBeGreaterThan(beforePreview)
    await expect(refresh).toBeEnabled()
    await app.evidence('cultivation-data-refresh-light')

    const catalogAfterSuccess = catalogRequests
    failureCode = 503
    await refresh.click()
    await expect(
      page.getByText(
        'Could not load data from the download site or Yituliu. Check the network and try again. Existing data is retained.',
        {
          exact: true,
        }
      )
    ).toBeVisible()
    await expect(refresh).toBeEnabled()
    expect(catalogRequests).toBe(catalogAfterSuccess)
    await expect(root.getByText('Updated operator', { exact: true }).first()).toBeVisible()

    failureCode = 507
    await refresh.click()
    await expect(
      page.getByText(
        'Could not save the data cache. Check disk space and folder permissions. Existing data is retained.',
        { exact: true }
      )
    ).toBeVisible()
    await expect(refresh).toBeEnabled()
    expect(catalogRequests).toBe(catalogAfterSuccess)
    failureCode = -1
    await refresh.click()
    await expect(
      page.getByText(
        'Refresh service is unavailable. Check the backend and try again. Existing data is retained.',
        { exact: true }
      )
    ).toBeVisible()
    await expect(refresh).toBeEnabled()
    failureCode = 0
    failCatalog = true
    await refresh.click()
    await expect(
      page.getByText('Data refreshed, but the page could not reload. Please try again.', {
        exact: true,
      })
    ).toBeVisible()
    await expect(refresh).toBeEnabled()
    await page.evaluate(async () => {
      const modulePath = '/src/composables/useTheme.ts'
      const { useTheme } = await import(modulePath)
      await useTheme().setThemeMode('dark')
    })
    await expect(page.locator('html')).toHaveClass(/dark/)
    await app.evidence('cultivation-data-refresh-dark')
  })
})
