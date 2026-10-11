import { expect, test } from './fixtures'

test.describe('@history search and view', () => {
  test('navigates to history page and shows empty state', async ({ app, page }) => {
    await app.goto('/history')
    // 等待懒加载路由真正渲染出页面根节点，再断言内容（frontend/src/views/history/index.vue:2）
    await expect(page.locator('.history-page')).toBeVisible()

    // 页面空态或记录列表必须真实渲染（index.vue:32、HistoryRecordList.vue:2）
    await expect(page.locator('.empty-state, .record-list-panel').first()).toBeVisible()

    await app.evidence('history-initial')
  })

  test('filters history by date range', async ({ app, page }) => {
    await app.goto('/history')
    await expect(page.locator('.history-page')).toBeVisible()

    // 页面挂载时自动检索一次（useHistoryLogic.ts:290-292），先等它结束再触发筛选
    await expect(page.locator('.empty-state, .record-list-panel').first()).toBeVisible()

    // 快捷时间按钮就是按日期区间筛选的入口：点击后写入起止日期并立即检索
    //（HistorySearchPanel.vue:7-15 → useHistoryLogic.ts:163-169）
    const searchResponse = page.waitForResponse(
      response =>
        response.url().includes('/api/history/search') && response.request().method() === 'POST'
    )
    await page.locator('.time-buttons button').first().click()
    expect((await searchResponse).ok()).toBeTruthy()

    await expect(page.locator('.empty-state, .record-list-panel').first()).toBeVisible()

    await app.evidence('history-filtered-by-date')
  })

  test('expands history item to view logs', async ({ app, page }) => {
    await app.goto('/history')
    await expect(page.locator('.history-page')).toBeVisible()

    // 展开日志需要先有历史数据：日期侧栏的账号项（HistoryDateSidebar.vue:22-27）
    const userItem = page.locator('.date-sidebar .user-item').first()
    test.skip((await userItem.count()) === 0, '当前数据根没有历史记录，无可展开项')

    await userItem.click()
    const recordItem = page.locator('.record-list-panel .record-item').first()
    await expect(recordItem).toBeVisible()

    // 点击记录打开日志弹窗（index.vue:181-189、HistoryLogModal.vue:12、:189/:199）
    await recordItem.click()
    await expect(page.locator('.log-modal-content')).toBeVisible()
    await expect(page.locator('.log-editor, .empty-log').first()).toBeVisible()

    await app.evidence('history-expanded')
  })

  // 历史页既没有文本搜索框，也没有独立的刷新按钮（HistorySearchPanel.vue 只有快捷时间、合并方式、
  // 起止日期与搜索/重置按钮），原「空搜索结果」「刷新列表」两个用例没有可断言的用户路径，故删除；
  // 重新检索的路径由上面的快捷时间用例覆盖。
})
