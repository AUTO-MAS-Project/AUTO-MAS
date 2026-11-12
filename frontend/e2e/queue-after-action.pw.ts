import { expect, test } from './fixtures'

test.describe('@queue completion settings', () => {
  test('shows delay only for an action and keeps the combined column allocation', async ({
    app,
    page,
  }) => {
    const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`
    const post = async (url: string, data: unknown = {}) => {
      const response = await page.request.post(`${backend}${url}`, { data })
      const body = (await response.json()) as { code: number; queueId: string }
      expect(body.code).toBe(200)
      return body
    }
    const { queueId } = await post('/api/queue/add')
    // Test action selection in the browser only: the backend always retains NoAction.
    const preview = { AfterAccomplish: 'NoAction', AfterAccomplishDelay: 7 }
    const writes: Partial<typeof preview>[] = []
    try {
      await post('/api/queue/update', {
        queueId,
        data: { Info: { Name: 'Completion preview', AfterAccomplishDelay: 7 } },
      })
      await page.route('**/api/queue/update', async route => {
        if (route.request().method() === 'OPTIONS') return route.continue()
        const request = route.request().postDataJSON() as {
          queueId: string
          data: { Info?: Partial<typeof preview> }
        }
        const info = request.data.Info
        if (
          request.queueId !== queueId ||
          !info ||
          (!('AfterAccomplish' in info) && !('AfterAccomplishDelay' in info))
        )
          return route.continue()
        writes.push({ ...info })
        Object.assign(preview, info)
        await route.fulfill({
          status: 200,
          headers: { 'Access-Control-Allow-Origin': '*' },
          contentType: 'application/json',
          body: JSON.stringify({ code: 200, status: 'success', message: '' }),
        })
      })
      await page.route('**/api/queue/get', async route => {
        if (route.request().method() === 'OPTIONS') return route.continue()
        const response = await route.fetch()
        const body = (await response.json()) as { data: Record<string, { Info: typeof preview }> }
        if (body.data[queueId]) Object.assign(body.data[queueId].Info, preview)
        await route.fulfill({ response, json: body })
      })
      await app.goto('/queue')
      const trigger = page.locator('.queue-trigger-settings')
      const action = trigger.locator('.after-action-select')
      const delay = trigger.locator('.after-action-delay input')
      await expect(action).toContainText('Do nothing')
      await expect(delay).toHaveCount(0)
      const widths = () =>
        trigger
          .locator(':scope > .ant-row > .ant-col')
          .evaluateAll(elements => elements.map(el => el.getBoundingClientRect().width))
      const original = await widths()
      const choose = async (label: string) => {
        const refreshed = page.waitForResponse(
          response =>
            response.url().endsWith('/api/queue/get') && response.request().method() === 'POST'
        )
        await action.locator('.ant-select-selector').click()
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(label, { exact: true })
          .click()
        await (await refreshed).json()
        await expect(action).toContainText(label)
      }
      await choose('Sleep')
      await expect(delay).toBeEnabled()
      await expect(delay).toHaveValue('7')
      expect(writes.at(-1)).toEqual({ AfterAccomplish: 'Sleep' })
      const expanded = await widths()
      expect(expanded).toHaveLength(original.length)
      expanded.forEach((width, index) => expect(width).toBeCloseTo(original[index], 0))
      const refreshed = page.waitForResponse(
        response =>
          response.url().endsWith('/api/queue/get') && response.request().method() === 'POST'
      )
      await delay.fill('9')
      await delay.press('Tab')
      await (await refreshed).json()
      expect(writes.at(-1)).toEqual({ AfterAccomplishDelay: 9 })
      await expect(delay).toHaveValue('9')
      await choose('Do nothing')
      await expect(delay).toHaveCount(0)
      const collapsed = await widths()
      collapsed.forEach((width, index) => expect(width).toBeCloseTo(original[index], 0))
      await choose('Sleep')
      await expect(delay).toHaveValue('9')
      expect(
        (await trigger.locator('.ant-input-number-group-wrapper.after-action-delay').boundingBox())!
          .height
      ).toBe(40)
      expect((await action.boundingBox())!.height).toBe(40)
      for (const theme of ['light', 'dark']) {
        await page.evaluate(async theme => {
          const module = '/src/composables/useTheme.ts'
          const { useTheme } = await import(module)
          await useTheme().setThemeMode(theme)
          await Promise.allSettled(
            document
              .getAnimations()
              .filter(animation => animation.effect?.getComputedTiming().iterations !== Infinity)
              .map(animation => animation.finished)
          )
        }, theme)
        await app.evidence(`completion-delay-${theme}`)
      }
      const actual = await page.request.post(`${backend}/api/queue/get`, { data: {} })
      const actualBody = (await actual.json()) as { data: Record<string, { Info: typeof preview }> }
      expect(actualBody.data[queueId].Info.AfterAccomplish).toBe('NoAction')
      expect(actualBody.data[queueId].Info.AfterAccomplishDelay).toBe(7)
    } finally {
      await post('/api/queue/delete', { queueId })
    }
  })
})
