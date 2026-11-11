import fs from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
const adapters = [
  ['MAA', 'maa'],
  ['SRC', 'src'],
  ['General', 'general'],
  ['Okww', 'okww'],
  ['OkNte', 'oknte'],
  ['MaaEnd', 'maaend'],
  ['MaaFW', 'maafw'],
  ['M9A', 'm9a'],
  ['MSS', 'mss'],
  ['HSR', 'hsr'],
  ['BetterGI', 'bettergi'],
  ['ZzzOd', 'zzzod'],
  ['BAAH', 'baah'],
  ['Whimbox', 'whimbox'],
]

test.describe('@account-editors', () => {
  for (const [type, segment] of adapters) {
    test(`${type} saves the common account fields and heading`, async ({ app, page }, testInfo) => {
      const post = async (path: string, data: unknown) => {
        const response = await page.request.post(`${backend}${path}`, { data })
        const body = await response.json()
        expect(body.code).toBe(200)
        return body
      }
      const saved = () =>
        page.waitForResponse(
          response =>
            response.request().method() === 'POST' &&
            new URL(response.url()).pathname === '/api/scripts/user/update'
        )
      const { scriptId } = await post('/api/scripts/add', { type })
      try {
        if (type === 'Okww') {
          const scriptRoot = testInfo.outputPath('okww-script')
          const configDir = path.join(scriptRoot, 'data/apps/ok-ww/working/configs')
          await fs.mkdir(configDir, { recursive: true })
          await fs.writeFile(path.join(configDir, 'e2e.json'), '{}')
          await post('/api/scripts/update', { scriptId, data: { Info: { RootPath: scriptRoot } } })
        }
        const { userId } = await post('/api/scripts/user/add', { scriptId })
        await app.goto(`/scripts/${scriptId}/users/${userId}/edit/${segment}`)
        const fields = page.locator('.user-basic-info-fields')
        await expect(fields).toHaveCount(1)
        const name = fields.locator('input.ant-input').first()
        await expect(name).toBeEnabled()
        const accountName = `${type} account with a long name for wrapping`
        await name.fill(accountName)
        const naming = saved()
        await name.blur()
        expect((await (await naming).json()).code).toBe(200)
        await expect(page.locator('.account-title h1')).toHaveText(accountName)
        await expect(page.locator('.user-edit-content .ant-card .account-heading')).toHaveCount(1)
        await expect(page.locator('.user-edit-header .account-heading')).toHaveCount(0)
        await expect(page.locator('.account-icon')).toBeVisible()
        const status = fields.locator('.ant-select')
        await status.click()
        const disabling = saved()
        await page
          .locator('.ant-select-dropdown:visible')
          .getByText('Disabled', { exact: true })
          .click()
        expect((await (await disabling).json()).code).toBe(200)
        const days = fields.getByRole('spinbutton')
        for (const value of ['7', '-1']) {
          await days.fill(value)
          const updating = saved()
          await days.blur()
          expect((await (await updating).json()).code).toBe(200)
        }
        const notes = fields.locator('textarea')
        for (const value of ['Temporary account note', '']) {
          await notes.fill(value)
          const updating = saved()
          await notes.blur()
          expect((await (await updating).json()).code).toBe(200)
        }
        await page.reload()
        await expect(name).toHaveValue(accountName)
        await expect(page.locator('.account-title h1')).toHaveText(accountName)
        await expect(status).toContainText('Disabled')
        await expect(days).toHaveValue('-1')
        await expect(notes).toHaveValue('')
        await page.setViewportSize({ width: 720, height: 900 })
        await expect(
          page.locator('.user-edit-header').getByRole('button', { name: /Back$/ })
        ).toBeInViewport()
        const widths = await fields
          .locator(':scope > .ant-row > .ant-col')
          .evaluateAll(cols => cols.slice(0, 3).map(col => col.getBoundingClientRect().width))
        expect(Math.max(...widths) - Math.min(...widths)).toBeLessThan(1)
        await app.evidence(`account-editor-${segment}-narrow`)
        if (type === 'MaaFW') {
          const updateUrl = '**/api/scripts/user/update'
          await page.route(
            updateUrl,
            route => route.fulfill({ json: { code: 500, message: 'E2E save rejected' } }),
            { times: 1 }
          )
          await notes.fill('Keep this draft after a failed save')
          await notes.blur()
          await expect(page.locator('.save-status-error')).toHaveText('Save failed')
          await expect(notes).toHaveValue('Keep this draft after a failed save')
          await expect(page.locator('.ant-message-error')).toContainText('E2E save rejected')
          let release!: () => void
          let received!: () => void
          const gate = new Promise<void>(resolve => {
            release = resolve
          })
          const intercepted = new Promise<void>(resolve => {
            received = resolve
          })
          await page.route(
            updateUrl,
            async route => {
              received()
              await gate
              await route.continue()
            },
            { times: 1 }
          )
          try {
            await notes.fill('Saved before leaving')
            await notes.blur()
            await intercepted
            await expect(page.locator('.save-status-saving')).toHaveText('Saving…')
            const back = page.locator('.user-edit-header').getByRole('button', { name: /Back$/ })
            await back.click()
            await expect(back).toHaveClass(/ant-btn-loading/)
            await expect(page).toHaveURL(new RegExp(`/users/${userId}/edit/${segment}$`))
            release()
            await expect(page).toHaveURL(/#\/scripts$/)
            await app.goto(`/scripts/${scriptId}/users/${userId}/edit/${segment}`)
            await expect(notes).toHaveValue('Saved before leaving')
          } finally {
            release()
          }
        }
      } finally {
        await app.goto('/scripts')
        await post('/api/scripts/delete', { scriptId })
      }
    })
  }
})
