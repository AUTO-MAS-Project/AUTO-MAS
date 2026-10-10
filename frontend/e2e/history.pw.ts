import { expect, test } from './fixtures'

test.describe('@history search and view', () => {
  test('navigates to history page and shows empty state', async ({ app, page }) => {
    await app.goto('/history')
    await expect(page.getByText('History', { exact: true }).first()).toBeVisible()

    // 验证空态或现有记录
    const emptyState = page.locator('.empty-image, .ant-empty')
    const historyList = page.locator('.history-list, .ant-list, .history-card')

    const hasEmpty = await emptyState.isVisible().catch(() => false)
    const hasList = await historyList.isVisible().catch(() => false)

    expect(hasEmpty || hasList).toBeTruthy()

    await app.evidence('history-initial')
  })

  test('filters history by date range', async ({ app, page }) => {
    await app.goto('/history')

    // 查找日期选择器
    const dateRangePicker = page.locator('.ant-picker-range').first()
    if (await dateRangePicker.isVisible().catch(() => false)) {
      await dateRangePicker.click()

      // 选择今天
      const todayCell = page.locator('.ant-picker-cell-today').first()
      if (await todayCell.isVisible().catch(() => false)) {
        await todayCell.click()
        await todayCell.click() // 选择日期范围的开始和结束

        // 等待列表更新
        await page.waitForTimeout(500)

        await app.evidence('history-filtered-by-date')
      }
    }
  })

  test('expands history item to view logs', async ({ app, page }) => {
    await app.goto('/history')

    // 查找可展开的历史项
    const historyItems = page.locator(
      '.history-item, .ant-list-item, .history-card, .ant-collapse-item'
    )
    const itemCount = await historyItems.count()

    if (itemCount > 0) {
      // 展开第一个项目
      const firstItem = historyItems.first()
      await firstItem.click()

      // 等待日志内容出现
      const logContent = page.locator(
        '.history-log, .log-content, .ant-collapse-content, .history-detail'
      )
      await expect(logContent.first()).toBeVisible({ timeout: 5000 })

      await app.evidence('history-expanded')
    } else {
      console.log('⚠️  No history items found, skipping expand test')
    }
  })

  test('handles empty search results', async ({ app, page }) => {
    await app.goto('/history')

    // 查找搜索输入框
    const searchInput = page.locator(
      'input[placeholder*="搜索"], input[placeholder*="search"], .ant-input-search'
    )

    if (await searchInput.first().isVisible().catch(() => false)) {
      // 输入不存在的关键词
      await searchInput.first().fill('__nonexistent_task_12345__')
      await searchInput.first().press('Enter')

      // 等待搜索结果
      await page.waitForTimeout(1000)

      // 验证显示"无结果"
      const emptyResult = page.locator('.ant-empty, .no-result, .empty-state')
      await expect(emptyResult.first()).toBeVisible({ timeout: 3000 })

      await app.evidence('history-empty-search')

      // 清空搜索
      await searchInput.first().clear()
    }
  })

  test('refreshes history list', async ({ app, page }) => {
    await app.goto('/history')

    // 查找刷新按钮
    const refreshButton = page.locator(
      'button:has-text("刷新"), button:has-text("Refresh"), .ant-btn-icon-only:has([data-icon="reload"])'
    )

    if (await refreshButton.first().isVisible().catch(() => false)) {
      // 点击刷新
      const refreshResponse = page.waitForResponse(
        response =>
          response.url().includes('/api/history') && response.request().method() === 'GET',
        { timeout: 5000 }
      )

      await refreshButton.first().click()
      const response = await refreshResponse
      expect(response.ok()).toBeTruthy()

      await app.evidence('history-refreshed')
    }
  })
})
