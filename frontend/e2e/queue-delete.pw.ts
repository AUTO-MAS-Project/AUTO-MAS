import { expect, test } from './fixtures'

test.describe('@queue delete confirmation', () => {
  test('deletes schedules, tasks and queues only after dialog confirmation', async ({
    app,
    page,
  }) => {
    const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36184'}`
    const post = async (url: string, data: unknown = {}) => {
      const response = await page.request.post(`${backend}${url}`, { data })
      const result = (await response.json()) as { code: number; queueId: string; timeSetId: string }
      expect(result.code).toBe(200)
      return result
    }
    const { queueId } = await post('/api/queue/add')
    let deleted = false
    try {
      await post('/api/queue/update', {
        queueId,
        data: { Info: { Name: 'Delete confirmation', TimeEnabled: true } },
      })
      const { timeSetId } = await post('/api/queue/time/add', { queueId })
      await post('/api/queue/time/update', {
        queueId,
        timeSetId,
        data: { Info: { Enabled: false } },
      })
      await post('/api/queue/item/add', { queueId })
      await app.goto('/queue')
      await page.locator('.queue-button').filter({ hasText: 'Delete confirmation' }).click()
      let requests = 0
      page.on('request', request => {
        if (
          request.method() === 'POST' &&
          /\/api\/queue\/(?:time\/|item\/)?delete$/.test(request.url())
        )
          requests += 1
      })
      const targets = [
        {
          button: page.locator('.time-set-card .actions-cell').getByRole('button'),
          endpoint: '/api/queue/time/delete',
          title: 'Delete this schedule?',
        },
        {
          button: page.locator('.queue-item-card .actions-cell').getByRole('button'),
          endpoint: '/api/queue/item/delete',
          title: 'Delete this task?',
        },
        {
          button: page.getByRole('button', { name: 'Delete this queue', exact: true }),
          endpoint: '/api/queue/delete',
          title: 'Delete this queue?',
        },
      ]
      for (const [index, target] of targets.entries()) {
        await target.button.click()
        const dialog = page.getByRole('dialog')
        await expect(dialog).toContainText(target.title)
        await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
        await expect(dialog).toBeHidden()
        await expect(page.locator('.ant-modal-confirm')).toHaveCount(0)
        expect(requests).toBe(index)
        await expect(target.button).toBeVisible()
        await target.button.click()
        const response = page.waitForResponse(
          result => result.url().endsWith(target.endpoint) && result.request().method() === 'POST'
        )
        await dialog.getByRole('button', { name: 'Delete', exact: true }).click()
        expect((await (await response).json()).code).toBe(200)
        await expect(dialog).toBeHidden()
        await expect(page.locator('.ant-modal-confirm')).toHaveCount(0)
        await expect(target.button).toHaveCount(0)
        expect(requests).toBe(index + 1)
      }
      deleted = true
    } finally {
      if (!deleted) await post('/api/queue/delete', { queueId })
    }
  })
})
