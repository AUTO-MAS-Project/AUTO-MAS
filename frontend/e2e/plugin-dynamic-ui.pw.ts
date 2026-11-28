import { expect, test } from './fixtures'

type Demo15Record = {
  uid: string
  info: { plugin_name: string; source: string; enabled: boolean; state: string }
  frontend: {
    activationId: string
    pages: Record<string, Record<string, { entry: string; panelApi: number }>>
  } | null
}

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@plugins @plugin-dynamic-ui demo15 dynamic UI end-to-end', () => {
  test.skip(
    process.env.AUTO_MAS_E2E_IN_PLACE === '1' || process.env.AUTO_MAS_E2E_REAL === '1',
    'Demo15 is staged by the isolated browser profile'
  )

  test('persists declarative and sandboxed plan edits and revokes the panel on disable', async ({
    app,
    page,
  }) => {
    await expect
      .poll(
        async () => {
          const response = await page.request.get(`${backend}/api/core/health`)
          return response.ok() ? (await response.json()).businessStatus : response.status()
        },
        { timeout: 30_000 }
      )
      .toBe('ready')

    const post = async <T = unknown>(endpoint: string, data: object): Promise<T> => {
      const response = await page.request.post(`${backend}${endpoint}`, { data })
      await expect(response).toBeOK()
      const body: T & { code: number; message: string } = await response.json()
      expect(body.code, `${endpoint}: ${body.message}`).toBe(200)
      return body
    }
    const getDemo15 = async () => {
      const { data } = await post<{ data: Record<string, Demo15Record> }>(
        '/api/plugin_registry/get',
        {}
      )
      return Object.values(data).find(record => record.info.plugin_name === 'demo15')
    }

    await expect.poll(getDemo15).toMatchObject({
      info: { source: 'local', enabled: false, state: 'disabled' },
    })
    const record = (await getDemo15())!
    const command = async (field: 'enable' | 'disable') => {
      const { data: taskId } = await post<{ data: string }>('/api/config/triggers/write', {
        configUid: record.uid,
        group: 'info',
        field,
        value: true,
      })
      await expect
        .poll(
          async () => {
            const { data } = await post<{ data: { state: string } }>(
              '/api/config/triggers/result',
              {
                taskId,
              }
            )
            return data
          },
          { message: `demo15 ${field} trigger` }
        )
        .toMatchObject({ state: 'succeeded' })
    }

    let scriptId: string | undefined
    let planId: string | undefined
    try {
      await command('enable')
      await expect.poll(getDemo15).toMatchObject({
        info: { enabled: true, state: 'enabled' },
        frontend: {
          activationId: expect.stringMatching(/\S/),
          pages: { plan: { web: { entry: 'plan.html', panelApi: 1 } } },
        },
      })

      await test.step('Save and reload the declarative script editor', async () => {
        const script = await post<{ scriptId: string }>('/api/scripts/add', { type: 'Demo15' })
        scriptId = script.scriptId
        await app.goto(`/scripts/${scriptId}/edit/plugin/Demo15`)

        const form = page.getByRole('region', { name: 'Plugin settings', exact: true })
        const openRunSettings = async () => {
          await form.getByRole('button', { name: 'Next', exact: true }).click()
          await form.getByRole('button', { name: 'Run', exact: true }).click()
        }
        await expect(form.getByText('Region', { exact: true })).toBeVisible()
        await expect(form.getByText('Profile', { exact: true })).toBeVisible()
        await openRunSettings()
        await expect(form.getByText('Mode', { exact: true })).toBeVisible()
        const retries = form.getByRole('spinbutton')
        await expect(retries).toHaveValue('0')
        await retries.fill('3')
        await form.getByRole('button', { name: 'Complete', exact: true }).click()
        await expect(page.getByText('Settings saved', { exact: true })).toBeVisible()

        await page.reload()
        await openRunSettings()
        await expect(retries).toHaveValue('3')
        await app.evidence('demo15-declarative-script')
      })

      const assetUrl = await test.step('Save and reload the sandboxed plan panel', async () => {
        const plan = await post<{ planId: string }>('/api/plan/add', { type: 'Demo15PlanConfig' })
        planId = plan.planId
        await app.goto(`/plans?planId=${planId}`)

        const frameSelector = 'iframe[title="demo15"]'
        const iframe = page.locator(frameSelector)
        await expect(iframe).toBeVisible()
        await expect(iframe).toHaveAttribute('sandbox', 'allow-scripts allow-forms')
        await expect(iframe).toHaveAttribute('referrerpolicy', 'no-referrer')
        await expect(iframe).toHaveAttribute(
          'src',
          /\/api\/plugin\/demo15\/ui\/[^/]+\/plan\.html(?:#|$)/
        )
        const url = new URL((await iframe.getAttribute('src'))!, backend)
        url.hash = ''
        await expect(await page.request.get(url.href)).toBeOK()

        const panel = page.frameLocator(frameSelector)
        const first = panel.locator('[data-group="First"]')
        const count = first.getByRole('spinbutton', { name: 'Count', exact: true })
        const enabled = first.getByRole('checkbox', { name: 'Enabled', exact: true })
        const save = panel.getByRole('button', { name: 'Save', exact: true })
        await expect(count).toHaveValue('1')
        await expect(enabled).toBeChecked()
        await expect(save).toBeEnabled()
        await expect(panel.locator('html')).toHaveAttribute('data-theme', /^(light|dark)$/)
        await expect(panel.locator('html')).toHaveCSS('--mas-bg-base', /\S/)

        await count.fill('5')
        await enabled.uncheck()
        await save.click()
        await expect(panel.getByRole('status')).toHaveText('Saved')

        await page.reload()
        await expect(count).toHaveValue('5')
        await expect(enabled).toBeEnabled()
        await expect(enabled).not.toBeChecked()
        await app.evidence('demo15-wheel-plan')
        return url.href
      })

      await command('disable')
      expect((await page.request.get(assetUrl)).status()).toBe(404)
    } finally {
      if ((await getDemo15())?.info.enabled) await command('disable')
      if (planId) await post('/api/plan/delete', { planId })
      if (scriptId) await post('/api/scripts/delete', { scriptId })
    }
  })
})
