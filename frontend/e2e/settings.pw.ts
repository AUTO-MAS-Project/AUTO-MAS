import type { Locator, Page } from '@playwright/test'
import type { InstalledAppearance } from '../src/types/appearance'
import type { ElectronAPI, RuntimeLaunchModeState } from '../src/types/electron'
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
  test('anchors question hints to the icon for hover and keyboard focus', async ({ app, page }) => {
    await app.goto('/settings')
    const popup = page.locator('.ant-tooltip:visible')
    const checkHint = async (icon: Locator) => {
      for (const keyboard of [false, true]) {
        if (keyboard) {
          await icon.focus()
          await page.keyboard.press('Shift+Tab')
          await page.keyboard.press('Tab')
          await expect(icon).toBeFocused()
        } else {
          await icon.hover()
        }
        await expect(popup).toBeVisible()
        await expect
          .poll(async () => {
            const target = await icon.boundingBox()
            const arrow = await popup.locator('.ant-tooltip-arrow').boundingBox()
            if (!target || !arrow) return Number.POSITIVE_INFINITY
            return Math.abs(arrow.x + arrow.width / 2 - target.x - target.width / 2)
          })
          .toBeLessThan(3)
        await icon.blur()
        await page.mouse.move(0, 0)
        await expect(popup).toHaveCount(0)
      }
    }

    // 列数由宽度决定：窄屏单列、宽屏两列，都检查问号提示。
    for (const layout of [{ width: 1440 }, { width: 1920 }]) {
      await page.setViewportSize({ width: layout.width, height: 891 })
      await checkHint(page.locator('.startup-options-row .ui-row-label .help-icon'))
      const autoStart = page.getByRole('checkbox', { name: 'Start with the system', exact: true })
      const checked = await autoStart.isChecked()
      await checkHint(page.locator('.startup-options-row .ant-checkbox-wrapper .help-icon'))
      await expect(autoStart).toBeChecked({ checked })
    }
    await checkHint(page.locator('.row-label .help-icon:visible'))
    await page.getByRole('tab', { name: 'Features', exact: true }).click()
    await checkHint(page.locator('.row-label .help-icon:visible'))
    await checkHint(page.locator('.card-note-hint .help-icon'))
    await page.getByRole('tab', { name: 'About', exact: true }).click()
    await checkHint(page.locator('.cdk-label .help-icon'))
    await app.evidence('settings-question-hints')
  })

  test('saves scheduled wake-up independently of login startup', async ({ app, page }) => {
    await app.goto('/settings')
    const wakeup = page.getByRole('switch', { name: 'Scheduled wake-up', exact: true })
    const autoStart = page.getByRole('checkbox', { name: 'Start with the system', exact: true })
    const loginEnabled = await autoStart.isChecked()
    for (const enabled of [true, false]) {
      const saved = settingsResponse(page, 'update')
      await wakeup.click()
      const response = await saved
      expect(response.request().postDataJSON()).toMatchObject({
        data: { Start: { IfScheduledWakeUp: enabled } },
      })
      expect((await response.json()).code).toBe(200)
      await page.reload()
      await expect(wakeup).toBeChecked({ checked: enabled })
      await expect(autoStart).toBeChecked({ checked: loginEnabled })
      await app.evidence(`scheduled-wakeup-${enabled ? 'enabled' : 'disabled'}`)
      if (enabled) {
        await page.getByRole('button', { name: 'Switch to dark mode', exact: true }).click()
        await expect(page.locator('html')).toHaveClass(/dark/)
        await app.evidence('scheduled-wakeup-dark')
        await page.getByRole('button', { name: 'Switch to light mode', exact: true }).click()
      }
    }
  })

  test('restores the persisted Runtime choice and allows switching back to auto', async ({
    app,
    page,
  }) => {
    await page.addInitScript(() => {
      const key = 'auto-mas.e2e.runtime-launch-mode'
      const readState = (): RuntimeLaunchModeState => {
        const persisted = localStorage.getItem(key) === 'auto' ? 'auto' : 'managed'
        return {
          persisted,
          mode: persisted === 'auto' ? 'development' : 'managed',
          source: persisted === 'auto' ? 'default' : 'setting',
        }
      }
      let bridge: ElectronAPI | undefined
      Object.defineProperty(window, 'electronAPI', {
        configurable: true,
        get: () => bridge,
        set: (base: ElectronAPI) => {
          bridge = {
            ...base,
            getRuntimeLaunchMode: async () => readState(),
            setRuntimeLaunchMode: async mode => {
              localStorage.setItem(key, mode)
              return readState()
            },
          }
        },
      })
    })
    await app.goto('/settings')
    await page.getByRole('tab', { name: 'Advanced', exact: true }).click()
    const control = page.locator('.ant-segmented[aria-label="Backend launch mode"]')
    await expect(control).toBeVisible()
    await expect(control.getByRole('radio')).toHaveCount(2)
    await expect(
      control.getByRole('radio', { name: 'Supervised by Runtime (managed)', exact: true })
    ).toBeChecked()
    await expect(page.locator('.mode-effective')).toContainText('Supervised by Runtime (managed)')
    await chooseSegment(control, 'Auto')
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem('auto-mas.e2e.runtime-launch-mode')))
      .toBe('auto')
    await page.reload()
    await page.getByRole('tab', { name: 'Advanced', exact: true }).click()
    await expect(control.getByRole('radio', { name: 'Auto', exact: true })).toBeChecked()
    await expect(page.locator('.mode-effective')).toContainText(
      'Supervised by Runtime (development)'
    )
    await expect(page.locator('.mode-effective')).toContainText(
      'Takes effect after restarting the app'
    )
    await chooseSegment(control, 'Supervised by Runtime (managed)')
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem('auto-mas.e2e.runtime-launch-mode')))
      .toBe('managed')
    await app.evidence('runtime-launch-mode-restored')
  })

  test('preserves appearance sidebar and title colors and restores the built-in theme', async ({
    app,
    page,
  }) => {
    const appearances: InstalledAppearance[] = [
      {
        formatVersion: 1,
        id: 'settings-light',
        name: 'Settings light appearance',
        mode: 'light',
        tokens: {
          colorPrimary: '#b45148',
          colorBgElevated: '#fff4dd',
          colorText: '#49352d',
          colorBorder: '#765432',
          colorPageTitle: '#b45148',
        },
      },
      {
        formatVersion: 1,
        id: 'settings-dark',
        name: 'Settings dark appearance',
        mode: 'dark',
        tokens: {
          colorPrimary: '#a78bfa',
          colorBgElevated: '#252038',
          colorText: '#eeeaf4',
          colorBorder: '#c4b5fd',
          colorPageTitle: '#c4b5fd',
        },
      },
    ]
    await page.addInitScript(appearances => {
      let bridge: ElectronAPI | undefined
      Object.defineProperty(window, 'electronAPI', {
        configurable: true,
        get: () => bridge,
        set: (base: ElectronAPI) => {
          bridge = {
            ...base,
            listAppearances: async () => appearances,
            getAppearance: async id => appearances.find(appearance => appearance.id === id) ?? null,
          }
        },
      })
    }, appearances)
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    await app.goto('/settings')
    const sider = page.locator('.app-sider')
    const title = page.locator('.settings-header h1')
    const selector = page.locator('.appearance-select')
    await expect(selector).toBeVisible()
    const builtInBackground = await sider.evaluate(
      element => getComputedStyle(element).backgroundColor
    )
    const builtInTitle = await title.evaluate(element => getComputedStyle(element).color)
    for (const appearance of appearances) {
      await chooseOption(page, selector, appearance.name)
      const light = appearance.mode === 'light'
      if (light) await expect(page.locator('html')).not.toHaveClass(/dark/)
      else await expect(page.locator('html')).toHaveClass(/dark/)
      await expect
        .soft(sider)
        .toHaveCSS('background-color', light ? 'rgb(255, 244, 221)' : 'rgb(37, 32, 56)', {
          timeout: 1000,
        })
      await expect
        .soft(sider)
        .toHaveCSS('border-right-color', light ? 'rgb(118, 84, 50)' : 'rgb(196, 181, 253)', {
          timeout: 1000,
        })
      await expect
        .soft(title)
        .toHaveCSS('color', light ? 'rgb(180, 81, 72)' : 'rgb(196, 181, 253)', { timeout: 1000 })
      await expect(page.locator('.theme-mode-control input').first()).toBeDisabled()
    }
    await chooseOption(page, selector, 'Default appearance')
    await expect(sider).toHaveCSS('background-color', builtInBackground)
    await expect(title).toHaveCSS('color', builtInTitle)
    await app.evidence('appearance-colors-restored')
  })

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

  test('preserves startup and appearance preferences with the shared header controls', async ({
    app,
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    const loaded = settingsResponse(page, 'get')
    await app.goto('/settings')
    const originalMinimize = (await (await loaded).json()).data.UI.IfToTray === true
    const minimize = page.locator('[aria-label="When minimizing"]')
    const toolbar = page.locator('.settings-page-toolbar')
    const sider = page.locator('.app-sider')
    const theme = page.locator('.theme-mode-control')
    const originalTheme = await theme.locator('.ant-segmented-item-selected').innerText()
    const originalAccent = await page
      .locator('.color-swatch[aria-pressed="true"]')
      .getAttribute('aria-label')
    try {
      for (const toTray of [!originalMinimize, originalMinimize]) {
        const saved = settingsResponse(page, 'update')
        await chooseSegment(minimize, toTray ? 'Minimize to tray' : 'Minimize to taskbar')
        const response = await saved
        expect(response.request().postDataJSON()).toMatchObject({
          data: { UI: { IfToTray: toTray } },
        })
        expect((await response.json()).code).toBe(200)
      }
      await expect(theme.getByRole('radio', { name: 'Follow system', exact: true })).toBeChecked()
      await expect(sider).toHaveCSS('background-color', 'rgb(242, 242, 242)')
      await page.getByRole('button', { name: 'Purple', exact: true }).click()
      await expect(sider).toHaveCSS('background-color', 'rgb(242, 242, 242)')
      await expect(sider).toHaveCSS('border-right-color', 'rgb(224, 224, 224)')
      await toolbar.getByRole('button', { name: 'Switch to dark mode', exact: true }).click()
      await expect(page.locator('html')).toHaveClass(/dark/)
      await expect(sider).toHaveCSS('background-color', 'rgb(20, 20, 20)')
      await expect(sider).toHaveCSS('border-right-color', 'rgb(48, 48, 48)')
      await expect(theme.getByRole('radio', { name: 'Dark', exact: true })).toBeChecked()
      await expect(page.getByRole('button', { name: 'Purple', exact: true })).toHaveAttribute(
        'aria-pressed',
        'true'
      )
      for (const tab of ['Features', 'Notifications', 'Advanced', 'About']) {
        await page.getByRole('tab', { name: tab, exact: true }).click()
        await expect(
          toolbar.getByRole('button', { name: 'Switch to light mode', exact: true })
        ).toBeVisible()
      }
      await toolbar.getByRole('button', { name: 'Switch to light mode', exact: true }).click()
      await expect(page.locator('html')).not.toHaveClass(/dark/)
      await expect(sider).toHaveCSS('background-color', 'rgb(242, 242, 242)')
      await page.getByRole('tab', { name: 'Interface', exact: true }).click()
      await expect(theme.getByRole('radio', { name: 'Light', exact: true })).toBeChecked()
      await page.setViewportSize({ width: 1040, height: 900 })
      await expect(
        toolbar.getByRole('button', { name: 'Switch to dark mode', exact: true })
      ).toBeVisible()
      // 目录显隐是持久化偏好，窄窗口不会把它自动收起
      await expect(page.getByRole('navigation', { name: 'Settings sections' })).toBeVisible()
      await page.reload()
      await expect(theme.getByRole('radio', { name: 'Light', exact: true })).toBeChecked()
      await expect(page.locator('.settings-section-layout')).toHaveAttribute(
        'data-effective-layout',
        'single'
      )
      await expect(page.getByRole('button', { name: 'Purple', exact: true })).toHaveAttribute(
        'aria-pressed',
        'true'
      )
      await app.evidence('settings-header-narrow-reloaded')
    } finally {
      await page.getByRole('tab', { name: 'Interface', exact: true }).click()
      const originalMinimizeLabel = originalMinimize ? 'Minimize to tray' : 'Minimize to taskbar'
      if (
        !(await minimize
          .getByRole('radio', { name: originalMinimizeLabel, exact: true })
          .isChecked())
      ) {
        const restored = settingsResponse(page, 'update')
        await chooseSegment(minimize, originalMinimizeLabel)
        expect((await (await restored).json()).code).toBe(200)
      }
      await chooseSegment(theme, originalTheme)
      if (originalAccent)
        await page.getByRole('button', { name: originalAccent, exact: true }).click()
    }
  })

  test('keeps section order and reflows columns by width without a layout switch', async ({
    app,
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await app.goto('/settings')
    const layout = page.locator('.settings-section-layout')
    const navigation = page.getByRole('navigation', { name: 'Settings sections' })
    const pane = page.locator('.ant-tabs-tabpane-active')
    const headings = pane.locator('.form-section > .section-header > h3')
    const cards = pane.locator('.tab-content > .form-section')

    // 布局开关已移除：只剩宽度决定列数。
    await expect(page.locator('[aria-label="Settings layout"]')).toHaveCount(0)
    await expect(page.locator('.settings-save-note')).toHaveCount(0)

    await expect(navigation).toBeVisible()
    await expect.poll(() => headings.count()).toBeGreaterThan(1)
    const order = (await headings.allTextContents()).map(title => title.trim())
    await expect(navigation.getByRole('button')).toHaveText(order)

    // 宽屏：目录在右侧，卡片两列
    await expect(layout).toHaveAttribute('data-effective-layout', 'dual')
    expect((await cards.nth(0).boundingBox())!.x).toBeLessThan(
      (await cards.nth(1).boundingBox())!.x
    )

    // 目录跳转仍可用
    const lastLink = navigation.getByRole('button').last()
    await lastLink.click()
    await expect(lastLink).toHaveAttribute('aria-current', 'location')
    await expect
      .poll(() => layout.locator('.ant-tabs-content-holder').evaluate(node => node.scrollTop))
      .toBeGreaterThan(0)
    await expect(headings.last()).toBeInViewport()

    // 切到功能页签，确认顺序不变、未保存输入保留
    await page.getByRole('tab', { name: 'Features', exact: true }).click()
    const featureOrder = (await headings.allTextContents()).map(title => title.trim())
    const draft = pane.locator('.number-input input').nth(1)
    const draftElement = await draft.elementHandle()
    const originalDraft = await draft.inputValue()
    await draft.fill('4096')

    // 窄屏：目录保留，卡片退回单列（目录不随宽度消失）
    await page.setViewportSize({ width: 1040, height: 900 })
    await expect(navigation).toBeVisible()
    await expect(page.getByText('On this page', { exact: true })).toBeVisible()
    await expect(layout).toHaveAttribute('data-effective-layout', 'single')
    await expect(headings).toHaveText(featureOrder)
    expect((await cards.nth(0).boundingBox())!.x).toBe((await cards.nth(1).boundingBox())!.x)
    await expect(draft).toHaveValue('4096')
    expect(await draftElement!.evaluate(node => node.isConnected)).toBe(true)
    await draft.fill(originalDraft)

    // 拉回宽屏：目录与两列自动恢复，无需任何开关操作
    await page.setViewportSize({ width: 1920, height: 1080 })
    await expect(navigation).toBeVisible()
    await expect(layout).toHaveAttribute('data-effective-layout', 'dual')

    await page.getByRole('tab', { name: 'About', exact: true }).click()
    await expect(navigation).toHaveCount(0)
    await app.evidence('settings-layout-about')
  })

  test('keeps the section navigation under user control instead of window width', async ({
    app,
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await app.goto('/settings')
    const layout = page.locator('.settings-section-layout')
    const navigation = page.getByRole('navigation', { name: 'Settings sections' })
    const toggle = page.locator('.settings-navigation-toggle')
    const restore = async () => {
      if ((await toggle.getAttribute('aria-pressed')) === 'false') await toggle.click()
    }
    await expect(navigation).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-pressed', 'true')
    try {
      // 缩放窗口只改列数，目录始终在
      for (const width of [1600, 1280, 1040, 960]) {
        await page.setViewportSize({ width, height: 900 })
        await expect(navigation).toBeVisible()
      }
      await expect(layout).toHaveAttribute('data-effective-layout', 'single')

      // 关掉目录后，窄窗口不再有目录，宽窗口仍可两列
      await page.setViewportSize({ width: 1920, height: 1080 })
      await toggle.click()
      await expect(toggle).toHaveAttribute('aria-pressed', 'false')
      await expect(navigation).toHaveCount(0)
      await expect(layout).toHaveAttribute('data-effective-layout', 'dual')
      await page.setViewportSize({ width: 1040, height: 900 })
      await expect(navigation).toHaveCount(0)
      await expect(layout).toHaveAttribute('data-effective-layout', 'single')

      // 偏好跨重载保留
      await page.reload()
      await expect(toggle).toHaveAttribute('aria-pressed', 'false')
      await expect(navigation).toHaveCount(0)
      await page.setViewportSize({ width: 1920, height: 1080 })
      await expect(toggle).toHaveAttribute('aria-pressed', 'false')
      await expect(navigation).toHaveCount(0)
      await app.evidence('settings-navigation-hidden')

      await restore()
      await expect(navigation).toBeVisible()
      await page.reload()
      await expect(toggle).toHaveAttribute('aria-pressed', 'true')
      await expect(navigation).toBeVisible()
      await app.evidence('settings-navigation-restored')
    } finally {
      await restore()
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
