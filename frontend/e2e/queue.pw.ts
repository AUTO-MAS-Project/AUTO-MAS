import { expect, test } from './fixtures'

const backendBaseUrl = () => `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`

type QueueIndexEntry = { uid: string; type: string }

type App = { api: { raw: import('@playwright/test').APIRequestContext } }

/** 直接问后端要队列列表：页面上看不出来「这条队列是谁造的数据」。 */
const readQueueIndex = async (app: App): Promise<QueueIndexEntry[]> => {
  const response = await app.api.raw.post(`${backendBaseUrl()}/api/queue/get`, { data: {} })
  const body = (await response.json()) as { code: number; index: QueueIndexEntry[] }
  expect(body.code, '查询队列列表失败').toBe(200)
  return body.index
}

test.describe('@queue persistence', () => {
  test('creates, renames, configures, and reloads a queue', async ({ app, page }) => {
    const queueUpdateResponse = () =>
      page.waitForResponse(
        response =>
          response.url().endsWith('/api/queue/update') &&
          response.request().method() === 'POST' &&
          response.ok()
      )

    await app.goto('/queue')

    // 空状态前置条件：整套用例共享同一个数据根，这里已经有队列就说明有别的用例留下了数据。
    // 直接点名是谁留下的，否则下一个人只会看到「No queues 找不到」然后从零开始排查。
    const leftover = await readQueueIndex(app)
    expect(
      leftover.map(entry => entry.uid),
      '队列页不是空状态：有别的用例留下了队列数据（造数据的用例必须在 finally 里删掉）'
    ).toEqual([])
    await expect(page.getByText('No queues', { exact: true })).toBeVisible()

    try {
      await page.getByRole('button', { name: 'New queue' }).click()
      await expect(
        page.getByRole('button', { name: /New queue|New scheduling queue/ })
      ).toBeVisible()
      const queueTitle = page.locator('.queue-title-text')
      await expect(queueTitle).toBeVisible()
      await page.locator('.queue-edit-btn').click()
      const nameInput = page.locator('.queue-title-input')
      await nameInput.fill('E2E queue')
      const renameResponse = queueUpdateResponse()
      await nameInput.press('Enter')
      await renameResponse
      await expect(queueTitle).toHaveText('E2E queue')

      const startupSelect = page
        .locator('.form-item-vertical')
        .filter({ hasText: 'Run at startup' })
        .locator('.ant-select-selector')
      await startupSelect.click()
      const alwaysResponse = queueUpdateResponse()
      await page
        .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: 'Run every time' })
        .click()
      await alwaysResponse
      await expect(
        page.locator('.ant-select-selection-item', { hasText: 'Run every time' })
      ).toBeVisible()

      await app.evidence('queue-configured')
      // 必须整页刷新才会重新从后端读配置：hash 路由来回切用的是内存里的旧数据，断言不到持久化
      await page.reload()
      await expect(page.locator('.queue-title-text')).toHaveText('E2E queue')
      await expect(
        page.locator('.ant-select-selection-item', { hasText: 'Run every time' })
      ).toBeVisible()
      await app.evidence('queue-reloaded')

      await startupSelect.click()
      const neverResponse = queueUpdateResponse()
      await page
        .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: 'Never' })
        .click()
      await neverResponse
      await expect(page.locator('.ant-select-selection-item', { hasText: 'Never' })).toBeVisible()
    } finally {
      // 这个用例自己造了一个队列，跑完必须删干净，否则下一个断言空状态的用例会看到它
      for (const entry of await readQueueIndex(app)) {
        await app.api.post('/api/queue/delete', { queueId: entry.uid })
      }
      expect(await readQueueIndex(app), '清理失败：队列数据还在，后面的用例会看到残留').toEqual([])
    }
  })
})
