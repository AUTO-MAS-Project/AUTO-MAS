import type { Locator, Page } from '@playwright/test'
import { expect, test } from './fixtures'

const chooseOption = async (page: Page, select: Locator, label: string) => {
  await select.click()
  await page.locator('.ant-select-dropdown:visible').getByText(label, { exact: true }).click()
  await expect(select.locator('.ant-select-selection-item')).toHaveText(label)
}

const chooseSegment = async (control: Locator, label: string) => {
  await control.getByText(label, { exact: true }).click()
  await expect(control.getByRole('radio', { name: label, exact: true })).toBeChecked()
}

const settingsResponse = (page: Page, action: 'get' | 'update') =>
  page.waitForResponse(
    response =>
      response.url().endsWith(`/api/setting/${action}`) && response.request().method() === 'POST'
  )

const backgroundColor = (page: Page) =>
  page.locator('body').evaluate(async body => {
    await Promise.all(body.getAnimations().map(animation => animation.finished))
    return getComputedStyle(body).backgroundColor
  })

test.describe('@settings user preferences', () => {
  test('changes the visible theme and retains it after navigation and reload', async ({
    app,
    page,
  }) => {
    await app.goto('/settings')
    const theme = page.locator('.theme-mode-control')
    await expect(theme).toBeVisible()
    const original = await theme.locator('.ant-segmented-item-selected').innerText()
    try {
      await chooseSegment(theme, 'Light')
      await expect(page.locator('html')).not.toHaveClass(/dark/)
      const lightBackground = await backgroundColor(page)

      await chooseSegment(theme, 'Dark')
      await expect(page.locator('html')).toHaveClass(/dark/)
      const darkBackground = await backgroundColor(page)
      expect(darkBackground).not.toBe(lightBackground)

      await page
        .getByRole('menuitem')
        .filter({ has: page.getByText('Home', { exact: true }) })
        .click()
      await expect(page.locator('.home-title')).toBeVisible()
      await page
        .getByRole('menuitem')
        .filter({ has: page.getByText('Settings', { exact: true }) })
        .click()
      await expect(theme.getByRole('radio', { name: 'Dark', exact: true })).toBeChecked()
      await page.reload()
      await expect(theme.getByRole('radio', { name: 'Dark', exact: true })).toBeChecked()
      await expect(page.locator('html')).toHaveClass(/dark/)
      await expect(page.locator('body')).toHaveCSS('background-color', darkBackground)
      await app.evidence('settings-dark-reloaded')
    } finally {
      await chooseSegment(theme, original)
    }
  })

  test('keeps section order, controls and layout preference across responsive changes', async ({
    app,
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await app.goto('/settings')
    const layout = page.locator('.settings-section-layout')
    const selector = page.locator('[aria-label="Settings layout"]')
    const navigation = page.getByRole('navigation', { name: 'Settings sections' })
    const pane = page.locator('.ant-tabs-tabpane-active')
    const headings = pane.locator('.form-section > .section-header > h3')
    const cards = pane.locator('.tab-content > .form-section')
    try {
      await expect(layout).toHaveAttribute('data-layout-mode', 'single')
      await expect(layout).toHaveAttribute('data-effective-layout', 'single')
      await expect(
        selector.getByRole('radio', { name: 'Single column', exact: true })
      ).toBeChecked()
      await expect(navigation).toBeVisible()
      await expect.poll(() => headings.count()).toBeGreaterThan(1)
      const order = (await headings.allTextContents()).map(title => title.trim())
      await expect(navigation.getByRole('button')).toHaveText(order)
      expect((await cards.nth(0).boundingBox())!.x).toBe((await cards.nth(1).boundingBox())!.x)

      const lastLink = navigation.getByRole('button').last()
      await lastLink.click()
      await expect(lastLink).toHaveAttribute('aria-current', 'location')
      await expect
        .poll(() => layout.locator('.ant-tabs-content-holder').evaluate(node => node.scrollTop))
        .toBeGreaterThan(0)
      await expect(headings.last()).toBeInViewport()

      await page.getByRole('tab', { name: 'Features', exact: true }).click()
      const featureOrder = (await headings.allTextContents()).map(title => title.trim())
      // 录像存储上限由独立的保存按钮提交，适合验证切换布局时保留未保存的输入。
      const draft = pane.locator('.number-input input').nth(1)
      const draftElement = await draft.elementHandle()
      const originalDraft = await draft.inputValue()
      await draft.fill('4096')
      await page.setViewportSize({ width: 1040, height: 900 })
      await expect(navigation).toHaveCount(0)
      await expect(page.getByText('On this page', { exact: true })).toHaveCount(0)
      await expect(draft).toHaveValue('4096')
      expect(await draftElement!.evaluate(node => node.isConnected)).toBe(true)

      await page.setViewportSize({ width: 1920, height: 1080 })
      await chooseSegment(selector, 'Two columns')
      await expect(layout).toHaveAttribute('data-layout-mode', 'dual')
      await expect(layout).toHaveAttribute('data-effective-layout', 'dual')
      await expect(navigation).toHaveCount(0)
      await expect(headings).toHaveText(featureOrder)
      expect((await cards.nth(0).boundingBox())!.x).toBeLessThan(
        (await cards.nth(1).boundingBox())!.x
      )
      await expect(draft).toHaveValue('4096')
      expect(await draftElement!.evaluate(node => node.isConnected)).toBe(true)
      await draft.fill(originalDraft)

      await page.setViewportSize({ width: 1040, height: 900 })
      await expect(layout).toHaveAttribute('data-layout-mode', 'dual')
      await expect(layout).toHaveAttribute('data-effective-layout', 'single')
      await expect(navigation).toHaveCount(0)
      await expect(page.getByText('On this page', { exact: true })).toHaveCount(0)
      await expect(headings).toHaveText(featureOrder)
      expect((await cards.nth(0).boundingBox())!.x).toBe((await cards.nth(1).boundingBox())!.x)

      await page.setViewportSize({ width: 1920, height: 1080 })
      await expect(layout).toHaveAttribute('data-effective-layout', 'dual')
      await page.reload()
      await expect(selector.getByRole('radio', { name: 'Two columns', exact: true })).toBeChecked()
      await expect(layout).toHaveAttribute('data-effective-layout', 'dual')
      for (const tab of ['Features', 'Notifications', 'Advanced']) {
        await page.getByRole('tab', { name: tab, exact: true }).click()
        await expect(
          selector.getByRole('radio', { name: 'Two columns', exact: true })
        ).toBeChecked()
        await expect(navigation).toHaveCount(0)
      }
      await page.getByRole('tab', { name: 'About', exact: true }).click()
      await expect(selector).toHaveCount(0)
      await expect(navigation).toHaveCount(0)
      await app.evidence('settings-layout-about')
    } finally {
      await page.getByRole('tab', { name: 'Interface', exact: true }).click()
      await chooseSegment(selector, 'Single column')
    }
  })

  for (const failure of [
    { name: 'business rejection', status: 200, message: 'Settings rejected' },
    { name: 'HTTP failure', status: 503, message: 'Settings unavailable' },
  ]) {
    test(`keeps the saved retention value after ${failure.name} and allows retry`, async ({
      app,
      page,
    }) => {
      const loaded = settingsResponse(page, 'get')
      await app.goto('/settings')
      const initial = (await (await loaded).json()).data.Function.HistoryRetentionTime as number
      await page.getByRole('tab', { name: 'Features', exact: true }).click()
      const retention = page.locator('.retention-select')
      const original = initial === 0 ? 'Keep forever' : `${initial} days`
      await expect(retention.locator('.ant-select-selection-item')).toHaveText(original)

      try {
        const baseline = settingsResponse(page, 'update')
        await chooseOption(page, retention, '30 days')
        expect((await (await baseline).json()).code).toBe(200)

        await page.route('**/api/setting/update', async route => {
          if (route.request().method() === 'OPTIONS') return route.continue()
          await route.fulfill({
            status: failure.status,
            headers: { 'Access-Control-Allow-Origin': '*' },
            contentType: 'application/json',
            body: JSON.stringify({ code: 500, status: 'error', message: failure.message }),
          })
        })
        const rejected = settingsResponse(page, 'update')
        await retention.click()
        await page
          .locator('.ant-select-dropdown:visible')
          .getByText('60 days', { exact: true })
          .click()
        expect((await (await rejected).json()).code).toBe(500)
        await expect(page.locator('.ant-message-error')).toContainText(failure.message)
        await expect(page.locator('.ant-message-success')).toHaveCount(0)
        await expect(retention.locator('.ant-select-selection-item')).toHaveText('30 days')
        await app.evidence(`settings-${failure.status}-rejected`)

        await page.unroute('**/api/setting/update')
        const retried = settingsResponse(page, 'update')
        await chooseOption(page, retention, '60 days')
        expect((await (await retried).json()).code).toBe(200)
        const reloaded = settingsResponse(page, 'get')
        await page.reload()
        expect((await (await reloaded).json()).data.Function.HistoryRetentionTime).toBe(60)
        await page.getByRole('tab', { name: 'Features', exact: true }).click()
        await expect(retention.locator('.ant-select-selection-item')).toHaveText('60 days')
      } finally {
        await page.unroute('**/api/setting/update')
        const restored = settingsResponse(page, 'update')
        await chooseOption(page, retention, original)
        expect((await (await restored).json()).code).toBe(200)
      }
    })
  }
})
