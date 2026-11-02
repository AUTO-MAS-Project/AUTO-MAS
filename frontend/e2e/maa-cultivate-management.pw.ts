import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@maa-cultivate-management', () => {
  test('injects goals on enable, preserves them on disable, and keeps loading width stable', async ({
    app,
    page,
  }) => {
    const script = await (
      await page.request.post(`${backend}/api/scripts/add`, { data: { type: 'MAA' } })
    ).json()
    const user = await (
      await page.request.post(`${backend}/api/scripts/user/add`, {
        data: { scriptId: script.scriptId },
      })
    ).json()
    let managed = false
    let targets = JSON.stringify([
      { operator_id: 'custom', goals: [{ kind: 'elite', target_id: '', to_level: 1 }] },
    ])
    const original = targets
    const patches: unknown[] = []
    let release: (() => void) | undefined
    await page.route('**/api/scripts/user/get', async route => {
      const response = await route.fetch()
      const payload = await response.json()
      const task = payload.data[user.userId]?.Task
      if (task)
        Object.assign(task, {
          CultivateAllOwned: managed,
          CultivateTargets: targets,
          CultivateSklandAccount: 'synthetic-account',
          CultivateSklandUid: 'synthetic-role',
        })
      await route.fulfill({ json: payload })
    })
    await page.route('**/api/scripts/user/update', async route => {
      const patch = route.request().postDataJSON().data.Task
      patches.push(patch)
      if (patch.CultivateAllOwned) {
        await new Promise<void>(resolve => {
          release = resolve
        })
        targets = JSON.stringify([
          ...JSON.parse(targets),
          {
            operator_id: 'owned',
            goals: [
              { kind: 'elite', target_id: '', to_level: 2 },
              { kind: 'skill', target_id: '', to_level: 7 },
            ],
          },
        ])
      }
      managed = patch.CultivateAllOwned
      await route.fulfill({ json: { code: 200 } })
    })
    await page.route('**/api/scripts/maa/cultivate/operators', route =>
      route.fulfill({
        json: {
          code: 200,
          data: ['custom', 'owned'].map(value => ({
            value,
            label: value === 'custom' ? 'Custom operator' : 'Owned operator',
            maxElite: 2,
            maxSkillLevel: 7,
            skills: [],
            modules: [],
          })),
        },
      })
    )
    await page.route('**/api/scripts/maa/cultivate/preview', route =>
      route.fulfill({
        json: {
          code: 200,
          stages: [],
          demands: [],
          unobtainable: [],
          hasProgression: false,
          progressions: [],
        },
      })
    )
    await page.route('**/api/scripts/maa/cultivate/skland/bindings', route =>
      route.fulfill({ json: { code: 200, data: [] } })
    )
    await page.route('**/api/scripts/maa/depot/items', route =>
      route.fulfill({ json: { code: 200, data: [] } })
    )
    await page.route('**/api/scripts/maa/depot/inventory', route =>
      route.fulfill({ json: { code: 200, data: [] } })
    )
    await app.goto(`/scripts/${script.scriptId}/users/${user.userId}/cultivate/maa`)
    const button = page.locator('.cultivate-manage-button')
    await expect(button.locator('.cultivate-manage-label')).toHaveText('Unmanaged')
    await expect(button).toBeEnabled()
    await button.scrollIntoViewIfNeeded()
    const idle = await button.boundingBox()
    const adjacent = await page
      .getByRole('button', { name: 'Import from clipboard', exact: true })
      .boundingBox()
    expect(idle?.width).toBe(adjacent?.width)
    expect(idle?.height).toBe(adjacent?.height)
    await button.click()
    await expect(button).toHaveClass(/ant-btn-loading/)
    await expect(button).toBeDisabled()
    const loading = await button.boundingBox()
    const loadingLabel = await button.locator(':scope > span').last().boundingBox()
    expect(loading?.width).toBe(idle?.width)
    expect(loading?.x).toBe(idle?.x)
    await expect.poll(() => typeof release).toBe('function')
    release?.()
    await expect(button).toBeEnabled()
    await expect(button.locator('.cultivate-manage-label')).toHaveText('Managed')
    const finishedLabel = await button.locator(':scope > span').last().boundingBox()
    expect(finishedLabel?.x).toBe(loadingLabel?.x)
    await expect(page.getByText('Owned operator', { exact: true }).first()).toBeVisible()
    expect(JSON.parse(targets)[0]).toEqual(JSON.parse(original)[0])
    const beforeDisable = targets
    await app.evidence('cultivate-management-light')
    await button.click()
    await expect(button.locator('.cultivate-manage-label')).toHaveText('Unmanaged')
    await expect(button).toBeEnabled()
    expect(targets).toBe(beforeDisable)
    expect(patches).toEqual([{ CultivateAllOwned: true }, { CultivateAllOwned: false }])
    expect((await button.boundingBox())?.width).toBe(idle?.width)
    await page.evaluate(async () => {
      const modulePath = '/src/composables/useTheme.ts'
      const { useTheme } = await import(modulePath)
      await useTheme().setThemeMode('dark')
    })
    await expect(page.locator('html')).toHaveClass(/dark/)
    await app.evidence('cultivate-management-dark')
  })
})
