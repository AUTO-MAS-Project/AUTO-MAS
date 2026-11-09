import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
const responseFor = (page: Page, path: string, scriptId: string) =>
  page.waitForResponse(
    response =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === path &&
      response.request().postDataJSON()?.scriptId === scriptId
  )

test.describe('@script-run-limits', () => {
  test('persists clamped retry and restored hard limit after input blur', async ({ app, page }) => {
    const post = async (path: string, data: unknown) => {
      const response = await page.request.post(`${backend}${path}`, { data })
      expect(response.ok()).toBe(true)
      const body = await response.json()
      expect(body.code).toBe(200)
      return body
    }
    const created = await post('/api/scripts/add', { type: 'General' })
    const scriptId: string = created.scriptId

    try {
      await app.goto(`/scripts/${scriptId}/edit/general`)
      const section = page.locator('.form-section').filter({
        has: page.getByRole('heading', { name: 'Run configuration', exact: true }),
      })
      const inputFor = (label: string) =>
        section
          .locator('.ant-form-item')
          .filter({ has: page.getByText(label, { exact: true }) })
          .getByRole('spinbutton')
      const retryLabel = 'Retry limit'
      const hardLabel = 'Per-account total run limit (minutes)'

      // 失焦会修正输入；回归曾把修正前的旧草稿保存，而界面显示新值。
      for (const edit of [
        { label: retryLabel, key: 'RunTimesLimit', input: '4', value: 4 },
        { label: retryLabel, key: 'RunTimesLimit', input: '0', value: 1 },
        { label: hardLabel, key: 'HardTimeLimit', input: '145', value: 145 },
        { label: hardLabel, key: 'HardTimeLimit', input: '', value: 120 },
      ]) {
        const input = inputFor(edit.label)
        await input.fill(edit.input)
        const saving = responseFor(page, '/api/scripts/update', scriptId)
        await input.blur()
        const response = await saving
        expect(response.request().postDataJSON()).toEqual({
          scriptId,
          data: { Run: { [edit.key]: edit.value } },
        })
        expect((await response.json()).code).toBe(200)
        await expect(input).toHaveValue(String(edit.value))
      }

      const expected = { ...created.data.Run, RunTimesLimit: 1, HardTimeLimit: 120 }
      expect((await post('/api/scripts/get', { scriptId })).data[scriptId].Run).toEqual(expected)
      const reloaded = responseFor(page, '/api/scripts/get', scriptId)
      await page.reload()
      expect((await (await reloaded).json()).data[scriptId].Run).toEqual(expected)
      await expect(inputFor(retryLabel)).toHaveValue('1')
      await expect(inputFor(hardLabel)).toHaveValue('120')
      await section.scrollIntoViewIfNeeded()
      await app.evidence('run-limits-blur-regression')
    } finally {
      await app.goto('/scripts')
      await post('/api/scripts/delete', { scriptId })
    }
  })
})
