import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@maa-event-template activity target editing', () => {
  test('preserves placeholder edits and restores material columns when an activity opens', async ({
    app,
    page,
  }) => {
    let active = false
    let itemCatalogFails = false
    await page.route('**/api/scripts/maa/depot/items', route =>
      route.fulfill({
        json: {
          code: itemCatalogFails ? 500 : 200,
          message: itemCatalogFails ? 'Item catalog unavailable' : '',
          data: itemCatalogFails ? [] : [{ label: 'New material', value: '30013' }],
        },
      })
    )
    await page.route('**/api/scripts/maa/depot/inventory', route =>
      route.fulfill({ json: { code: 200, data: [{ label: '54321', value: '30013' }] } })
    )
    const activity = {
      Display: 'NEW-1',
      Value: 'NEW-1',
      Drop: '30013',
      DropName: 'New material',
      Activity: {
        Tip: '',
        StageName: 'New activity',
        UtcStartTime: '2026/10/20 12:00:00',
        UtcExpireTime: '2026/11/20 03:59:59',
        TimeZone: 8,
      },
    }
    await page.route('**/api/info/get/overview*', route =>
      route.fulfill({
        json: {
          code: 200,
          status: 'success',
          data: {
            StageByServer: {
              Official: {
                Activity: active ? [activity] : [],
                ActivityTemplate: active ? [] : ['material', 'material', 'orundum'],
                ActivityStatus: active ? 'ready' : 'empty',
                Resource: [],
                Options: [],
              },
            },
            Proxy: {},
          },
        },
      })
    )
    const created = await (
      await page.request.post(`${backend}/api/scripts/add`, { data: { type: 'MAA' } })
    ).json()
    expect(created.code).toBe(200)
    const scriptId: string = created.scriptId
    const user = await (
      await page.request.post(`${backend}/api/scripts/user/add`, { data: { scriptId } })
    ).json()
    expect(user.code).toBe(200)
    const updated = await page.request.post(`${backend}/api/scripts/user/update`, {
      data: {
        scriptId,
        userId: user.userId,
        data: {
          Info: { Name: 'isolated activity target', IfQuickConfig: true, Server: 'Official' },
        },
      },
    })
    expect((await updated.json()).code).toBe(200)
    const openEditor = async () => {
      const row = page.locator('.stamina-pipeline > .task-row').first()
      await row.locator('.row-main').first().click()
      return page.locator('.event-plan-editor')
    }
    await app.goto(`/scripts/${scriptId}/users/${user.userId}/edit/maa`)
    const editor = await openEditor()
    await expect(editor.locator('.plan-row')).toHaveCount(3)
    await expect(editor.locator('.event-item-text')).toHaveCount(0)
    await expect(editor.locator('.stock-value')).toHaveCount(0)
    await expect(editor).not.toContainText('New material')
    await expect(editor).not.toContainText('54321')
    await expect(editor.locator('.stage-name').first()).not.toHaveText('NEW-1')
    const saved = page.waitForResponse(
      response =>
        response.url().endsWith('/api/scripts/user/update') &&
        !!response.request().postDataJSON()?.data?.Task?.EventDepotMaintainPlans
    )
    await editor.getByRole('spinbutton').first().fill('250')
    await editor.getByRole('spinbutton').first().blur()
    expect((await (await saved).json()).code).toBe(200)
    const skipped = page.waitForResponse(
      response =>
        response.url().endsWith('/api/scripts/user/update') &&
        !!response.request().postDataJSON()?.data?.Task?.EventDepotMaintainPlans
    )
    await editor.getByRole('checkbox').nth(1).uncheck()
    expect((await (await skipped).json()).code).toBe(200)
    await app.evidence('maa-activity-placeholder')
    await page.reload()
    await openEditor()
    await expect(editor.getByRole('spinbutton').first()).toHaveValue('250')
    await expect(editor.getByRole('checkbox').nth(1)).not.toBeChecked()
    active = true
    await page.reload()
    await openEditor()
    await expect(editor.locator('.plan-row')).toHaveCount(1)
    await expect(editor.locator('.event-item-text')).toHaveText('New material')
    await expect(editor.locator('.stock-value')).toHaveCount(1)
    await expect(editor.locator('.stock-value')).toHaveText('54321')
    await expect(editor.getByRole('spinbutton')).toHaveValue('250')
    await app.evidence('maa-activity-current')
    itemCatalogFails = true
    await page.reload()
    await openEditor()
    await expect(editor).toContainText('Item catalog unavailable')
    await expect(editor.locator('.event-item-text')).toHaveText('New material')
  })
})
