import { expect, test } from './fixtures'

test.describe('@queue boolean controls', () => {
  test('keeps button saves, disabled states, keyboard actions and error rollback', async ({
    app,
    page,
  }) => {
    const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36184'}`
    const post = async (url: string, data: unknown = {}) => {
      const response = await page.request.post(`${backend}${url}`, { data })
      const result = (await response.json()) as { code: number; queueId: string }
      expect(result.code).toBe(200)
      return result
    }
    const { queueId } = await post('/api/queue/add')
    try {
      await post('/api/queue/update', {
        queueId,
        data: { Info: { Name: 'Bool feedback', TimeEnabled: true, AfterAccomplishDelay: 7 } },
      })
      await post('/api/queue/time/add', { queueId })
      await post('/api/queue/update', { queueId, data: { Info: { TimeEnabled: false } } })
      await app.goto('/queue')
      await page.locator('.queue-button').filter({ hasText: 'Bool feedback' }).click()
      const timed = page
        .locator('.queue-trigger-settings .ant-form-item')
        .filter({ hasText: 'Run on schedule' })
        .getByRole('button')
      const status = page.locator('.time-set-card .setting-toggle-button').first()
      await expect(timed).toHaveAttribute('aria-pressed', 'false')
      await expect(page.locator('.time-set-card')).toHaveCount(0)
      await page.route('**/api/queue/update', async route => {
        if (route.request().method() === 'OPTIONS') return route.continue()
        await route.fulfill({
          status: 200,
          headers: { 'Access-Control-Allow-Origin': '*' },
          contentType: 'application/json',
          body: JSON.stringify({ code: 400, message: 'Rejected preview setting' }),
        })
      })
      await timed.click()
      await expect(page.locator('.ant-message-error')).toContainText('Rejected preview setting')
      await expect(timed).toHaveAttribute('aria-pressed', 'false')
      await expect(page.locator('.time-set-card')).toHaveCount(0)
      await page.unroute('**/api/queue/update')

      let release = () => {}
      const gate = new Promise<void>(resolve => {
        release = resolve
      })
      let requests = 0
      await page.route('**/api/queue/update', async route => {
        if (route.request().method() === 'OPTIONS') return route.continue()
        requests += 1
        await gate
        await route.continue()
      })
      await timed.click()
      await expect(timed).toHaveClass(/ant-btn-loading/)
      await timed.dispatchEvent('click')
      expect(requests).toBe(1)
      release()
      await expect(status).toBeEnabled()
      await expect(timed).not.toHaveClass(/ant-btn-loading/)
      expect(requests).toBe(1)
      await page.unroute('**/api/queue/update')
      await page.route('**/api/queue/time/update', async route => {
        if (route.request().method() === 'OPTIONS') return route.continue()
        await route.fulfill({
          status: 200,
          headers: { 'Access-Control-Allow-Origin': '*' },
          contentType: 'application/json',
          body: JSON.stringify({ code: 400, message: 'Rejected preview status' }),
        })
      })
      await status.click()
      await expect(
        page.locator('.ant-message-error').filter({ hasText: 'Rejected preview status' })
      ).toBeVisible()
      await expect(status).toHaveAttribute('aria-pressed', 'true')
      await page.unroute('**/api/queue/time/update')
      await status.focus()
      await status.press('Space')
      await expect(status).toHaveAttribute('aria-pressed', 'false')
      await page.reload()
      await page.locator('.queue-button').filter({ hasText: 'Bool feedback' }).click()
      await expect(status).toHaveAttribute('aria-pressed', 'false')
      const formHeights = await page
        .locator('.queue-trigger-settings')
        .evaluate(element =>
          [
            ...element.querySelectorAll(
              '.ant-select-selector, .setting-toggle-button, .ant-input-number-group-wrapper, input.ant-input, .ant-btn'
            ),
          ].map(control => Math.round(control.getBoundingClientRect().height))
        )
      expect(formHeights).toHaveLength(4)
      expect(formHeights.every(height => height === 40)).toBe(true)
      const topRows = await page
        .locator('.queue-trigger-settings > .ant-row > .ant-col')
        .evaluateAll(elements => elements.map(element => element.getBoundingClientRect().top))
      expect(topRows).toHaveLength(4)
      expect(topRows.every(top => Math.abs(top - topRows[0]) < 1)).toBe(true)
      const delay = page.locator('.after-action-delay input')
      await expect(delay).toHaveCount(0)
      await expect(page.locator('.queue-cycle-settings')).toHaveCount(0)
      const extraFields = page.locator('.queue-config-card .form-section')
      expect(
        (await extraFields.locator('.setting-toggle-button').first().boundingBox())!.height
      ).toBe(40)
      expect((await extraFields.locator('input').first().boundingBox())!.height).toBe(40)
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
        await page.locator('.queue-trigger-settings').scrollIntoViewIfNeeded()
        await app.evidence(`queue-bool-${theme}`)
        await page.locator('.queue-config-card .form-section').scrollIntoViewIfNeeded()
        await app.evidence(`queue-bool-extra-${theme}`)
      }
      await page.setViewportSize({ width: 760, height: 720 })
      const extra = page.locator('.queue-config-card .form-section')
      await extra.scrollIntoViewIfNeeded()
      const toggleBox = await extra.locator('.setting-toggle-button').first().boundingBox()
      const inputBox = await extra.locator('input').first().boundingBox()
      expect(toggleBox!.x + toggleBox!.width).toBeLessThanOrEqual(inputBox!.x)
      await app.evidence('queue-bool-narrow')
      const narrowTrigger = page.locator('.queue-trigger-settings')
      await narrowTrigger.scrollIntoViewIfNeeded()
      // Ant Row 的 gutter 允许超出表单边界；检查实际控件，而非栅格的滚动宽度。
      const controlsInBounds = await narrowTrigger.evaluate(element => {
        const form = element.getBoundingClientRect()
        return [
          ...element.querySelectorAll(
            '.ant-select-selector, .setting-toggle-button, .ant-input-number-group-wrapper'
          ),
        ].every(control => {
          const box = control.getBoundingClientRect()
          return box.left >= form.left - 1 && box.right <= form.right + 1
        })
      })
      expect(controlsInBounds).toBe(true)
      await app.evidence('queue-triggers-narrow')
    } finally {
      await post('/api/queue/delete', { queueId })
    }
  })
})
