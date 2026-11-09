import { expect, test } from './fixtures'

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
    await expect(page.getByText('No queues', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: 'New queue' }).click()
    await expect(page.getByRole('button', { name: /New queue|New scheduling queue/ })).toBeVisible()
    const queueTitle = page.locator('.queue-title-text')
    await expect(queueTitle).toBeVisible()
    await page.locator('.queue-edit-btn').click()
    const nameInput = page.locator('.queue-title-input')
    await nameInput.fill('PR 队列验证')
    const renameResponse = queueUpdateResponse()
    await nameInput.press('Enter')
    await renameResponse
    await expect(queueTitle).toHaveText('PR 队列验证')

    const startupSelect = page
      .locator('.queue-trigger-settings .ant-form-item')
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

    const timerCard = page.locator('.time-set-card')
    await expect(timerCard).toHaveCount(0)
    const timedToggle = page
      .locator('.queue-trigger-settings .ant-form-item')
      .filter({ hasText: 'Run on schedule' })
      .getByRole('button')
    const cyclicToggle = page
      .locator('.queue-trigger-settings .ant-form-item')
      .filter({ hasText: 'Cycle trigger' })
      .getByRole('button')
    const interval = page
      .locator('.queue-cycle-settings .ant-form-item')
      .filter({ hasText: 'Cycle interval' })
      .getByRole('spinbutton')
    const reset = page.getByRole('button', { name: 'Reset', exact: true })
    await expect(page.locator('.queue-cycle-settings')).toHaveCount(0)
    const enableTimed = queueUpdateResponse()
    await timedToggle.click()
    await enableTimed
    await expect(timerCard.getByRole('button').first()).toBeEnabled()
    const added = page.waitForResponse(response => response.url().endsWith('/api/queue/time/add'))
    await timerCard.getByRole('button').first().click()
    expect((await (await added).json()).code).toBe(200)
    const timeStatus = timerCard.locator('.setting-toggle-button').first()
    await expect(timeStatus).toHaveAttribute('aria-pressed', 'true')
    const disableTime = page.waitForResponse(
      response =>
        response.url().endsWith('/api/queue/time/update') && response.request().method() === 'POST'
    )
    await timeStatus.click()
    expect((await (await disableTime).json()).code).toBe(200)
    await expect(timeStatus).toHaveAttribute('aria-pressed', 'false')
    const enableCycle = queueUpdateResponse()
    await cyclicToggle.click()
    await enableCycle
    await expect(interval).toBeEnabled()
    const intervalSaved = page.waitForResponse(
      response =>
        response.url().endsWith('/api/queue/update') &&
        response.request().postDataJSON()?.data?.Cycle?.IntervalMinutes === 90
    )
    await interval.fill('90')
    await interval.press('Tab')
    expect((await (await intervalSaved).json()).code).toBe(200)
    await page.reload()
    await expect(interval).toHaveValue('90')
    const hideCycle = queueUpdateResponse()
    await cyclicToggle.click()
    await hideCycle
    await expect(page.locator('.queue-cycle-settings')).toHaveCount(0)
    await expect(timerCard).toBeVisible()
    const showCycle = queueUpdateResponse()
    await cyclicToggle.click()
    await showCycle
    await expect(interval).toHaveValue('90')
    const sectionOrder = await page
      .locator('.queue-config-card')
      .evaluate(element =>
        [
          '.queue-trigger-settings',
          '.time-set-card',
          '.queue-cycle-settings',
          '.queue-item-card',
          '.queue-extra-settings',
        ].map(selector => element.querySelector(selector)!.getBoundingClientRect().top)
      )
    expect(sectionOrder.every((top, index) => index === 0 || top > sectionOrder[index - 1])).toBe(
      true
    )
    await app.evidence('queue-groups-enabled')
    await expect(timedToggle).toHaveAttribute('aria-pressed', 'true')
    await expect(timerCard.getByRole('button').first()).toBeEnabled()
    const resetResponse = page.waitForResponse(
      response =>
        response.url().endsWith('/api/queue/update') &&
        response.request().postDataJSON()?.data?.Cycle?.ResetTimer === true
    )
    await reset.click()
    expect((await (await resetResponse).json()).code).toBe(200)
    const disableTimed = queueUpdateResponse()
    await timedToggle.click()
    await disableTimed
    await expect(timerCard).toHaveCount(0)

    await expect(cyclicToggle).toHaveAttribute('aria-pressed', 'true')
    await expect(reset).toBeEnabled()

    await app.evidence('queue-configured')
    // 必须整页刷新才会重新从后端读配置：hash 路由来回切用的是内存里的旧数据，断言不到持久化
    await page.reload()
    await expect(page.locator('.queue-title-text')).toHaveText('PR 队列验证')
    await expect(
      page.locator('.ant-select-selection-item', { hasText: 'Run every time' })
    ).toBeVisible()
    await expect(timedToggle).toHaveAttribute('aria-pressed', 'false')
    await expect(cyclicToggle).toHaveAttribute('aria-pressed', 'true')
    await expect(timerCard).toHaveCount(0)
    const restoreTimed = queueUpdateResponse()
    await timedToggle.click()
    await restoreTimed
    await expect(timeStatus).toHaveAttribute('aria-pressed', 'false')
    const restoreHidden = queueUpdateResponse()
    await timedToggle.click()
    await restoreHidden
    await expect(timerCard).toHaveCount(0)
    const extraToggle = page
      .locator('.queue-config-card .form-section .setting-toggle-button')
      .first()
    await expect(extraToggle).toHaveAttribute('aria-pressed', 'false')
    const beforeScriptResponse = queueUpdateResponse()
    await extraToggle.click()
    expect((await (await beforeScriptResponse).json()).code).toBe(200)
    await expect(extraToggle).toHaveAttribute('aria-pressed', 'true')
    const beforeScriptOff = queueUpdateResponse()
    await extraToggle.click()
    expect((await (await beforeScriptOff).json()).code).toBe(200)
    await expect(extraToggle).toHaveAttribute('aria-pressed', 'false')
    await app.evidence('queue-reloaded')

    await startupSelect.click()
    const neverResponse = queueUpdateResponse()
    await page
      .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
      .filter({ hasText: 'Never' })
      .click()
    await neverResponse
    await expect(page.locator('.ant-select-selection-item', { hasText: 'Never' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(timerCard).toHaveCount(0)
    await page.locator('.queue-cycle-settings').scrollIntoViewIfNeeded()
    await app.evidence('queue-time-settings-hidden')
    await page.evaluate(async () => {
      const themeModule = '/src/composables/useTheme.ts'
      const { useTheme } = await import(themeModule)
      await useTheme().setThemeMode('dark')
      await Promise.allSettled(
        document
          .getAnimations()
          .filter(animation => animation.effect?.getComputedTiming().iterations !== Infinity)
          .map(animation => animation.finished)
      )
    })
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect(timerCard).toHaveCount(0)
    await app.evidence('queue-cycle-settings-dark')
    await page.locator('.queue-trigger-settings').scrollIntoViewIfNeeded()
    await app.evidence('queue-triggers-dark')
  })
})
