import fs from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@okww-arguments', () => {
  for (const mode of ['MAS', 'OKWW_SINGLE', 'OKWW']) {
    test(`confirms, persists and reloads custom arguments in ${mode}`, async ({ app, page }) => {
      const post = async (endpoint: string, data: unknown) => {
        const response = await page.request.post(`${backend}${endpoint}`, { data })
        expect(response.ok()).toBe(true)
        const body = await response.json()
        expect(body.code, body.message).toBe(200)
        return body
      }
      const { scriptId } = await post('/api/scripts/add', { type: 'Okww' })
      const install = path.join(path.dirname(process.env.AUTO_MAS_E2E_DATA_ROOT!), `okww-${mode}`)
      const appDir = path.join(install, 'data/apps/ok-ww')
      await fs.mkdir(path.join(appDir, 'working/configs'), { recursive: true })
      await fs.writeFile(path.join(install, 'ok-ww.exe'), '')
      await fs.writeFile(path.join(appDir, 'app.json'), '{"current_version":"v3.8.0-beta.1"}')
      await fs.writeFile(path.join(appDir, 'working/configs/DailyTask.json'), '{}')
      await post('/api/scripts/update', {
        scriptId,
        data: { Info: { RootPath: install }, Game: { AccountSwitchMethod: mode } },
      })
      const { userId } = await post('/api/scripts/user/add', { scriptId })
      await app.goto(`/scripts/${scriptId}/users/${userId}/edit/okww`)
      const field = page.locator('.ant-form-item').filter({
        has: page.getByRole('group', { name: 'Launch arguments', exact: true }),
      })
      const input = field.getByRole('textbox')
      const toggle = field.getByRole('switch', { name: 'Custom arguments', exact: true })
      const original = `-t ${mode === 'MAS' ? 'DailyTask' : 'MultiAccountConfigTask'} -e`
      await expect(input).toHaveValue(original)
      await expect(input).toHaveAttribute('readonly')
      await expect(toggle).toBeEnabled()

      await toggle.click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toContainText('Changing launch arguments may prevent ok-ww')
      await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
      await expect(toggle).not.toBeChecked()
      await expect(input).toHaveValue(original)

      await page.route(
        '**/api/scripts/user/update',
        route =>
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ code: 400, status: 'error', message: 'E2E save rejected' }),
          }),
        { times: 1 }
      )
      await toggle.click()
      const rejected = page.waitForResponse(response =>
        response.url().endsWith('/api/scripts/user/update')
      )
      await dialog.getByRole('button', { name: 'OK', exact: true }).click()
      expect((await (await rejected).json()).code).toBe(400)
      await expect(dialog).not.toBeVisible()
      await expect(toggle).not.toBeChecked()
      await expect(input).toHaveValue(original)
      await expect(toggle).toBeEnabled()

      await toggle.click()
      const enabled = page.waitForResponse(
        response =>
          response.url().endsWith('/api/scripts/user/update') &&
          response.request().method() === 'POST'
      )
      await dialog.getByRole('button', { name: 'OK', exact: true }).click()
      expect((await (await enabled).json()).code).toBe(200)
      await expect(dialog).not.toBeVisible()
      await expect(toggle).toBeChecked()
      await expect(input).toHaveValue(original)
      await expect(input).not.toHaveAttribute('readonly')

      await input.fill('"unfinished')
      await expect(field).toContainText('No closing quotation')
      const custom = '-t "Other Task" -h --'
      await input.fill(custom)
      const saved = page.waitForResponse(
        response =>
          response.url().endsWith('/api/scripts/user/update') &&
          response.request().method() === 'POST'
      )
      await input.blur()
      expect((await (await saved).json()).code).toBe(200)
      await page.reload()
      await expect(toggle).toBeChecked()
      await expect(input).toHaveValue(custom)
      const preview = await post('/api/scripts/okww/startup-arguments', {
        scriptId,
        custom: true,
        arguments: custom,
      })
      expect(preview.arguments).toEqual(['-t', 'Other Task', '-h', '--'])
      await expect(toggle).toBeEnabled()
      await field.scrollIntoViewIfNeeded()
      await app.evidence(`okww-custom-arguments-${mode}`)

      const disabled = page.waitForResponse(
        response =>
          response.url().endsWith('/api/scripts/user/update') &&
          response.request().method() === 'POST'
      )
      await toggle.click()
      expect((await (await disabled).json()).code).toBe(200)
      await expect(input).toHaveValue(original)
      await expect(input).toHaveAttribute('readonly')
    })
  }
})
