import dayjs from 'dayjs'
import { expect, test } from './fixtures'

test.describe('@history search and view', () => {
  test.skip(
    process.env.AUTO_MAS_E2E_IN_PLACE === '1' || process.env.AUTO_MAS_E2E_REAL === '1',
    '已知历史种子仅供普通隔离模式'
  )
  test('finds known runs by date and shows the selected status and log', async ({ app, page }) => {
    const responseFor = (action: 'search' | 'detail') =>
      page.waitForResponse(
        response =>
          response.url().endsWith(`/api/history/${action}`) &&
          response.request().method() === 'POST'
      )
    const preset = async (name: string) => {
      const searched = responseFor('search')
      await page.locator('.time-buttons').getByRole('button', { name, exact: true }).click()
      expect((await (await searched).json()).code).toBe(200)
    }
    const panels = page.locator('.date-panel')
    const selectAccount = async (index: number, name: string) => {
      const panel = panels.nth(index)
      const account = panel.locator('.user-item').filter({ hasText: name })
      if (!(await account.isVisible())) await panel.locator('.ant-collapse-header').click()
      await account.click()
    }
    const log = page.locator('.log-modal-content')
    const openLog = async (marker: string, status: string) => {
      const detail = responseFor('detail')
      await page.locator('.record-item').filter({ hasText: marker }).click()
      expect((await (await detail).json()).code).toBe(200)
      await expect(log.locator('.header-info .ant-tag')).toHaveText(status)
      await expect(log.locator('.view-lines')).toContainText(marker)
      for (const other of ['E2E_TODAY_SUCCESS', 'E2E_YESTERDAY_FAILURE', 'E2E_OLDER_SUCCESS']) {
        if (other !== marker) await expect(log.locator('.view-lines')).not.toContainText(other)
      }
    }
    const closeLog = async () => {
      await page.locator('.ant-modal:visible .ant-modal-close').click()
      await expect(log).toBeHidden()
    }

    const loaded = responseFor('search')
    await app.goto('/history')
    expect((await (await loaded).json()).code).toBe(200)
    await preset('Today')
    await expect(panels).toHaveCount(1)
    await selectAccount(0, 'History account A')
    await expect(page.locator('.record-item')).toHaveCount(1)
    await expect(page.locator('.record-item')).toContainText('E2E_TODAY_SUCCESS')
    await openLog('E2E_TODAY_SUCCESS', 'Done')
    await closeLog()

    await preset('Last week')
    await expect(panels).toHaveCount(2)
    await selectAccount(0, 'History account A')
    await expect(page.locator('.record-item')).toHaveCount(1)
    await expect(page.locator('.record-item')).toContainText('E2E_TODAY_SUCCESS')
    await selectAccount(1, 'History account A')
    await expect(page.locator('.record-item')).toHaveCount(1)
    await expect(page.locator('.record-item')).toContainText('E2E_YESTERDAY_FAILURE')
    await openLog('E2E_YESTERDAY_FAILURE', 'Failed')
    await app.evidence('history-failure-log')
    await closeLog()

    const dates = page.locator('.filter-section .ant-picker input')
    const setDate = async (index: number, date: string) => {
      const months = dayjs(await dates.nth(index).inputValue())
        .startOf('month')
        .diff(dayjs(date).startOf('month'), 'month')
      await dates.nth(index).click()
      const calendar = page.locator('.ant-picker-dropdown:visible')
      for (let month = 0; month < Math.abs(months); month++) {
        await calendar
          .locator(months > 0 ? '.ant-picker-header-prev-btn' : '.ant-picker-header-next-btn')
          .click()
      }
      await calendar.locator(`td[title="${date}"]`).click()
      await expect(dates.nth(index)).toHaveValue(date)
      await expect(calendar).toBeHidden()
    }
    await setDate(0, dayjs().subtract(9, 'day').format('YYYY-MM-DD'))
    let searched = responseFor('search')
    await page
      .locator('.filter-actions')
      .getByRole('button', { name: /Search$/ })
      .click()
    expect((await (await searched).json()).code).toBe(200)
    await expect(panels).toHaveCount(3)
    await selectAccount(2, 'History account B')
    await openLog('E2E_OLDER_SUCCESS', 'Done')
    await closeLog()

    await setDate(0, dayjs().subtract(30, 'day').format('YYYY-MM-DD'))
    await setDate(1, dayjs().subtract(20, 'day').format('YYYY-MM-DD'))
    searched = responseFor('search')
    await page
      .locator('.filter-actions')
      .getByRole('button', { name: /Search$/ })
      .click()
    expect((await (await searched).json()).code).toBe(200)
    await expect(page.locator('.history-page .empty-state')).toBeVisible()
    await expect(panels).toHaveCount(0)
    await preset('Today')
    await selectAccount(0, 'History account A')
    await openLog('E2E_TODAY_SUCCESS', 'Done')
    await closeLog()
  })
})
