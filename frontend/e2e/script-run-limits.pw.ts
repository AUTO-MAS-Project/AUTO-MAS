import type { Page, Request } from '@playwright/test'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
const scripts = [
  { type: 'OkNte', route: 'oknte' },
  { type: 'Okww', route: 'okww' },
  { type: 'BetterGI', route: 'bettergi' },
  { type: 'General', route: 'general' },
  { type: 'ZzzOd', route: 'zzzod' },
]
const fields = [
  { key: 'HardTimeLimit', label: 'Per-account total run limit (minutes)', value: 145 },
  { key: 'ProxyTimesLimit', label: 'Runs per day', value: 2 },
  { key: 'RunTimesLimit', label: 'Retry limit', value: 4 },
  { key: 'RunTimeLimit', label: 'Run timeout (minutes)', value: 83 },
] as const

const isScriptRequest = (request: Request, path: string, scriptId: string) =>
  request.method() === 'POST' &&
  new URL(request.url()).pathname === path &&
  request.postDataJSON()?.scriptId === scriptId

const responseFor = (page: Page, path: string, scriptId: string) =>
  page.waitForResponse(response => isScriptRequest(response.request(), path, scriptId))

test.describe('@script-run-limits', () => {
  for (const script of scripts) {
    test(`${script.type} preserves single-field saves and restores a cleared hard limit`, async ({
      app,
      page,
    }) => {
      const post = async (path: string, data: unknown) => {
        const response = await page.request.post(`${backend}${path}`, { data })
        expect(response.ok()).toBe(true)
        const body = await response.json()
        expect(body.code).toBe(200)
        return body
      }
      const created = await post('/api/scripts/add', { type: script.type })
      const scriptId: string = created.scriptId
      expect(scriptId).toBeTruthy()

      try {
        const loaded = responseFor(page, '/api/scripts/get', scriptId)
        await app.goto(`/scripts/${scriptId}/edit/${script.route}`)
        expect((await (await loaded).json()).code).toBe(200)
        const section = page.locator('.form-section').filter({
          has: page.getByRole('heading', { name: 'Run configuration', exact: true }),
        })
        const inputFor = (label: string) =>
          section
            .locator('.ant-form-item')
            .filter({ has: page.getByText(label, { exact: true }) })
            .getByRole('spinbutton')
        await expect(inputFor(fields[0].label)).toBeEnabled()

        const writes: unknown[] = []
        const recordWrite = (request: Request) => {
          if (isScriptRequest(request, '/api/scripts/update', scriptId)) {
            writes.push(request.postDataJSON())
          }
        }
        page.on('request', recordWrite)

        try {
          for (const field of fields) {
            const input = inputFor(field.label)
            await input.fill(String(field.value))
            await expect(input).toHaveValue(String(field.value))
            const saving = responseFor(page, '/api/scripts/update', scriptId)
            await input.blur()
            const response = await saving
            expect(response.request().postDataJSON()).toEqual({
              scriptId,
              data: { Run: { [field.key]: field.value } },
            })
            expect((await response.json()).code).toBe(200)
          }

          for (const boundary of [
            { key: 'RunTimesLimit', label: fields[2].label, input: '0', value: 1 },
            { key: 'RunTimeLimit', label: fields[3].label, input: '10000', value: 9999 },
            { key: 'HardTimeLimit', label: fields[0].label, input: '0', value: 1 },
          ]) {
            const input = inputFor(boundary.label)
            await input.fill(boundary.input)
            await expect(input).toHaveValue(boundary.input)
            const saving = responseFor(page, '/api/scripts/update', scriptId)
            await input.blur()
            const response = await saving
            const patch = response.request().postDataJSON()
            await test.info().attach(`clamped-${boundary.key}-request`, {
              body: JSON.stringify(patch, null, 2),
              contentType: 'application/json',
            })
            expect(patch).toEqual({
              scriptId,
              data: { Run: { [boundary.key]: boundary.value } },
            })
            expect((await response.json()).code).toBe(200)
            await expect(input).toHaveValue(String(boundary.value))
          }

          const hardLimit = inputFor(fields[0].label)
          await hardLimit.fill('')
          const restoring = responseFor(page, '/api/scripts/update', scriptId)
          await hardLimit.blur()
          const restored = await restoring
          expect(restored.request().postDataJSON()).toEqual({
            scriptId,
            data: { Run: { HardTimeLimit: 120 } },
          })
          expect((await restored.json()).code).toBe(200)
          await expect(hardLimit).toHaveValue('120')

          const expected = {
            ...created.data.Run,
            HardTimeLimit: 120,
            ProxyTimesLimit: 2,
            RunTimesLimit: 1,
            RunTimeLimit: 9999,
          }
          const stored = await post('/api/scripts/get', { scriptId })
          expect(stored.data[scriptId].Run).toEqual(expected)
          const reloaded = responseFor(page, '/api/scripts/get', scriptId)
          await page.reload()
          expect((await (await reloaded).json()).data[scriptId].Run).toEqual(expected)
          for (const field of fields) {
            await expect(inputFor(field.label)).toHaveValue(String(expected[field.key]))
          }
          expect(writes).toHaveLength(8)
          await section.scrollIntoViewIfNeeded()
          await app.evidence(`run-limits-${script.route}-reloaded`)
        } finally {
          page.off('request', recordWrite)
        }
      } finally {
        await app.goto('/scripts')
        await post('/api/scripts/delete', { scriptId })
      }
    })
  }
})
