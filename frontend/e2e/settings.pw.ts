import type { Locator, Page } from '@playwright/test'
import type { InstalledAppearance } from '../src/types/appearance'
import type { ElectronAPI } from '../src/types/electron'
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
      for (const name of ['Start with the system', 'Silent startup']) {
        const control = page.getByRole('checkbox', { name, exact: true })
        const checked = await control.isChecked()
        const row = page.locator('.setting-item').filter({ has: control })
        await checkHint(row.locator('.help-icon'))
        await expect(control).toBeChecked({ checked })
      }
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
    const loaded = settingsResponse(page, 'get')
    await app.goto('/settings')
    const initialResponse = await loaded
    const originalStart = (await initialResponse.json()).data.Start
    const backend = new URL(initialResponse.url()).origin
    const wakeup = page.getByRole('checkbox', { name: 'Scheduled wake-up', exact: true })
    const autoStart = page.getByRole('checkbox', { name: 'Start with the system', exact: true })
    const silentStart = page.getByRole('checkbox', { name: 'Silent startup', exact: true })
    try {
      // 旧版本允许仅定时唤醒并保留静默偏好，重新载入后必须仍能独立修改。
      const seeded = await page.request.post(`${backend}/api/setting/update`, {
        data: {
          data: {
            Start: { IfSelfStart: false, IfScheduledWakeUp: true, IfMinimizeDirectly: true },
          },
        },
      })
      expect((await seeded.json()).code).toBe(200)
      await page.reload()
      await expect(silentStart).toBeChecked()
      for (const [control, key, values] of [
        [silentStart, 'IfMinimizeDirectly', [false, true]],
        [wakeup, 'IfScheduledWakeUp', [false, true]],
        [autoStart, 'IfSelfStart', [true, false]],
      ] as const) {
        for (const enabled of values) {
          await expect(control).toBeEnabled()
          const saved = settingsResponse(page, 'update')
          await control.click()
          const response = await saved
          expect(response.request().postDataJSON()).toEqual({ data: { Start: { [key]: enabled } } })
          expect((await response.json()).code).toBe(200)
          await expect(control).toBeChecked({ checked: enabled })
          await page.reload()
          await expect(autoStart).toBeChecked({ checked: key === 'IfSelfStart' && enabled })
          await expect(wakeup).toBeChecked({ checked: key !== 'IfScheduledWakeUp' || enabled })
          await expect(silentStart).toBeChecked({
            checked: key !== 'IfMinimizeDirectly' || enabled,
          })
          await expect(silentStart).toBeEnabled()
        }
      }
      await app.evidence('scheduled-wakeup-silent-preference')
    } finally {
      const restored = await page.request.post(`${backend}/api/setting/update`, {
        data: { data: { Start: originalStart } },
      })
      expect((await restored.json()).code).toBe(200)
    }
  })

  test('persists press sound preferences and rolls back a rejected save before retry', async ({
    app,
    page,
  }) => {
    await app.goto('/settings')
    const section = page
      .locator('.form-section')
      .filter({ has: page.getByRole('heading', { name: 'Press sound', exact: true }) })
    const enabled = section.getByRole('switch', { name: 'Play sound', exact: true })
    const preset = section.locator('.preset-select')
    const volume = section.getByRole('slider')
    const readPreferences = () =>
      page.evaluate(async () => {
        const config = await window.electronAPI.loadConfig()
        return {
          enabled: config?.pressSoundEnabled,
          preset: config?.pressSoundPreset,
          volume: config?.pressSoundVolume,
        }
      })

    await expect(enabled).not.toBeChecked()
    await enabled.click()
    await expect.poll(async () => (await readPreferences()).enabled).toBe(true)
    await chooseOption(page, preset, 'Sound 1')
    await expect.poll(async () => (await readPreferences()).preset).toBe('fx1')
    await volume.press('Home')
    await expect.poll(async () => (await readPreferences()).volume).toBe(0)
    await expect(volume).toBeEnabled()
    await volume.press('ArrowRight')
    await expect.poll(async () => (await readPreferences()).volume).toBe(0.05)

    await page.reload()
    await expect(enabled).toBeChecked()
    await expect(preset.locator('.ant-select-selection-item')).toHaveText('Sound 1')
    await expect(volume).toHaveAttribute('aria-valuenow', '0.05')
    await expect.poll(readPreferences).toEqual({ enabled: true, preset: 'fx1', volume: 0.05 })

    // 保留浏览器桥接的配置存储，只在 IPC 写入边界拒绝一笔音效关闭。
    await page.evaluate(() => {
      const saveConfig = window.electronAPI.saveConfig
      let rejectNextDisable = true
      window.electronAPI.saveConfig = async (config, defaults) => {
        if (
          rejectNextDisable &&
          config !== null &&
          typeof config === 'object' &&
          'pressSoundEnabled' in config &&
          config.pressSoundEnabled === false
        ) {
          rejectNextDisable = false
          throw new Error('E2E press sound write rejected')
        }
        await saveConfig(config, defaults)
      }
    })
    await enabled.click()
    await expect(page.locator('.ant-message-error')).toContainText(
      'Could not save the press sound settings'
    )
    await expect(enabled).toBeChecked()
    await expect(enabled).toBeEnabled()
    expect(await readPreferences()).toEqual({ enabled: true, preset: 'fx1', volume: 0.05 })
    await section.scrollIntoViewIfNeeded()
    await app.evidence('press-sound-save-rejected')

    await enabled.click()
    await expect.poll(async () => (await readPreferences()).enabled).toBe(false)
    await page.reload()
    await expect(enabled).not.toBeChecked()
    await expect(preset.locator('.ant-select-selection-item')).toHaveText('Sound 1')
    await expect(volume).toHaveAttribute('aria-valuenow', '0.05')
    await expect.poll(readPreferences).toEqual({ enabled: false, preset: 'fx1', volume: 0.05 })
    await section.scrollIntoViewIfNeeded()
    await app.evidence('press-sound-retry-reloaded')
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

  test('preserves close and appearance preferences through their settings', async ({
    app,
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    const loaded = settingsResponse(page, 'get')
    await app.goto('/settings')
    const initial = (await (await loaded).json()).data
    const originalToTray = initial.UI.IfToTray
    const closeBehavior = page.locator('[aria-label="When closing"]')
    const closeConfirmation = page.getByRole('checkbox', {
      name: 'Confirm before closing',
      exact: true,
    })
    const readClosePreferences = () =>
      page.evaluate(async () => {
        const config = await window.electronAPI.loadConfig()
        return {
          lastCloseAction: config?.lastCloseAction,
          confirmBeforeClose: config?.confirmBeforeClose,
        }
      })
    await expect(closeConfirmation).toBeEnabled()
    await expect(closeBehavior.getByRole('radio')).toHaveCount(2)
    const initialClose = await readClosePreferences()
    const originalClose = {
      lastCloseAction: initialClose.lastCloseAction ?? 'quit',
      confirmBeforeClose: initialClose.confirmBeforeClose ?? true,
    }
    const closeLabel = (action: 'quit' | 'tray') =>
      action === 'quit' ? 'Quit immediately' : 'Minimize to tray'
    const header = page.locator('.settings-shell-header')
    const sider = page.locator('.app-sider')
    const theme = page.locator('.theme-mode-control')
    const originalTheme = await theme.locator('.ant-segmented-item-selected').innerText()
    const originalAccent = await page
      .locator('.color-swatch[aria-pressed="true"]')
      .getAttribute('aria-label')
    try {
      for (const action of [
        originalClose.lastCloseAction === 'quit' ? 'tray' : 'quit',
        originalClose.lastCloseAction,
      ] as const) {
        await expect(
          closeBehavior.getByRole('radio', { name: closeLabel(action), exact: true })
        ).toBeEnabled()
        await chooseSegment(closeBehavior, closeLabel(action))
        await expect(closeBehavior.getByRole('radio', { checked: true })).toHaveCount(1)
        const expectedClose = { ...originalClose, lastCloseAction: action }
        await expect.poll(readClosePreferences).toEqual(expectedClose)
        await expect(closeConfirmation).toBeChecked({ checked: originalClose.confirmBeforeClose })

        const reloaded = settingsResponse(page, 'get')
        await page.reload()
        expect((await (await reloaded).json()).data.UI.IfToTray).toBe(originalToTray)
        await expect(
          closeBehavior.getByRole('radio', { name: closeLabel(action), exact: true })
        ).toBeChecked()
        await expect(closeConfirmation).toBeChecked({ checked: originalClose.confirmBeforeClose })
        await expect.poll(readClosePreferences).toEqual(expectedClose)
      }

      for (const enabled of [!originalClose.confirmBeforeClose, originalClose.confirmBeforeClose]) {
        await closeConfirmation.setChecked(enabled)
        const expectedClose = { ...originalClose, confirmBeforeClose: enabled }
        await expect.poll(readClosePreferences).toEqual(expectedClose)
        await page.reload()
        await expect(closeConfirmation).toBeChecked({ checked: enabled })
        await expect.poll(readClosePreferences).toEqual(expectedClose)
      }

      if (originalClose.confirmBeforeClose) {
        await page.locator('.window-controls .close-button').click()
        const prompt = page
          .getByRole('dialog')
          .filter({ hasText: 'When clicking the close button:' })
        const defaultLabel =
          originalClose.lastCloseAction === 'quit' ? 'Close MAS' : 'Minimize MAS to tray'
        await expect(prompt.getByRole('radio', { name: defaultLabel, exact: true })).toBeChecked()
        await prompt
          .getByText(defaultLabel === 'Close MAS' ? 'Minimize MAS to tray' : 'Close MAS', {
            exact: true,
          })
          .click()
        await prompt.getByRole('checkbox', { name: "Don't show again", exact: true }).check()
        await prompt.getByRole('button', { name: 'Cancel', exact: true }).click()
        await expect(prompt).toBeHidden()
        await expect.poll(readClosePreferences).toEqual(originalClose)
      }

      await expect(theme.getByRole('radio', { name: 'Follow system', exact: true })).toBeChecked()
      await expect(sider).toHaveCSS('background-color', 'rgb(242, 242, 242)')
      await page.getByRole('button', { name: 'Purple', exact: true }).click()
      await expect(sider).toHaveCSS('background-color', 'rgb(242, 242, 242)')
      await expect(sider).toHaveCSS('border-right-color', 'rgb(224, 224, 224)')
      await chooseSegment(theme, 'Dark')
      await expect(page.locator('html')).toHaveClass(/dark/)
      await expect(sider).toHaveCSS('background-color', 'rgb(20, 20, 20)')
      await expect(sider).toHaveCSS('border-right-color', 'rgb(48, 48, 48)')
      await expect(theme.getByRole('radio', { name: 'Dark', exact: true })).toBeChecked()
      await page.locator('.startup-window-settings').scrollIntoViewIfNeeded()
      await app.evidence('settings-close-options-dark')
      await expect(page.getByRole('button', { name: 'Purple', exact: true })).toHaveAttribute(
        'aria-pressed',
        'true'
      )
      for (const tab of ['Features', 'Notifications', 'Advanced', 'About']) {
        await page.getByRole('tab', { name: tab, exact: true }).click()
        await expect(header.getByRole('button')).toHaveCount(0)
        await expect(page.locator('html')).toHaveClass(/dark/)
        if (tab === 'Advanced') {
          await expect(
            page.getByRole('button', { name: 'Open DevTools', exact: true })
          ).toBeVisible()
          await expect(page.getByText('Backend launch mode', { exact: true })).toHaveCount(0)
        }
      }
      await page.getByRole('tab', { name: 'Interface', exact: true }).click()
      await chooseSegment(theme, 'Light')
      await expect(page.locator('html')).not.toHaveClass(/dark/)
      await expect(sider).toHaveCSS('background-color', 'rgb(242, 242, 242)')
      await expect(theme.getByRole('radio', { name: 'Light', exact: true })).toBeChecked()
      await page.setViewportSize({ width: 1040, height: 900 })
      await expect(header.getByRole('button')).toHaveCount(0)
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
      const prompt = page.locator('.app-close-prompt-modal .ant-modal:visible')
      if (await prompt.isVisible()) {
        await prompt.getByRole('button', { name: 'Cancel', exact: true }).click()
      }
      await page.evaluate(async preferences => {
        await window.electronAPI.saveConfig(preferences)
      }, originalClose)
      const restoredRead = settingsResponse(page, 'get')
      await page.reload()
      const restoredSettings = (await (await restoredRead).json()).data
      expect(restoredSettings.UI.IfToTray).toBe(originalToTray)
      await expect.poll(readClosePreferences).toEqual(originalClose)
      await chooseSegment(theme, originalTheme)
      if (originalAccent)
        await page.getByRole('button', { name: originalAccent, exact: true }).click()
    }
  })

  test('persists update choices and keeps the newer CDK draft through saves and retry', async ({
    app,
    page,
  }) => {
    await page.route('**/api/setting/mirror-cdk', async route => {
      if (route.request().method() === 'OPTIONS') return route.continue()
      await route.fulfill({
        headers: { 'Access-Control-Allow-Origin': '*' },
        json: { code: 200, status: 'success', data: { status: 'invalid', expiredTime: null } },
      })
    })
    const loaded = settingsResponse(page, 'get')
    await app.goto('/settings')
    const initialResponse = await loaded
    const initial = (await initialResponse.json()).data.Update
    const original = {
      Channel: initial.Channel,
      Source: initial.Source,
      MirrorChyanCDK: initial.MirrorChyanCDK,
    }
    const backend = new URL(initialResponse.url()).origin
    const channelValue = original.Channel === 'beta' ? 'stable' : 'beta'
    const channelLabel = channelValue === 'stable' ? 'Stable' : 'Beta'
    const olderDraft = 'e2e-settings-older-cdk'
    const newerDraft = 'e2e-settings-newer-cdk'
    let releaseOlderSave!: () => void
    const olderSaveGate = new Promise<void>(resolve => {
      releaseOlderSave = resolve
    })

    try {
      await page.getByRole('tab', { name: 'About', exact: true }).click()
      const channel = page
        .locator('.ui-row')
        .filter({ has: page.getByText('Update channel', { exact: true }) })
        .locator('.ant-segmented')
      const channelSaved = settingsResponse(page, 'update')
      await chooseSegment(channel, channelLabel)
      const channelResponse = await channelSaved
      expect(channelResponse.request().postDataJSON()).toEqual({
        data: { Update: { Channel: channelValue } },
      })
      expect((await channelResponse.json()).code).toBe(200)

      const source = page.locator('.source-cards')
      const sources =
        original.Source === 'MirrorChyan' ? ['GitHub', 'MirrorChyan'] : ['MirrorChyan']
      for (const value of sources) {
        const sourceSaved = settingsResponse(page, 'update')
        await source.getByText(value, { exact: true }).click()
        const sourceResponse = await sourceSaved
        expect(sourceResponse.request().postDataJSON()).toEqual({
          data: { Update: { Source: value } },
        })
        expect((await sourceResponse.json()).code).toBe(200)
      }
      const cdk = page.getByPlaceholder('Enter the MirrorChyan CDK to use the Mirror source', {
        exact: true,
      })
      await expect(cdk).toBeEnabled()

      let olderSaveStarted!: () => void
      const olderSaving = new Promise<void>(resolve => {
        olderSaveStarted = resolve
      })
      let rejectNextSave = true
      await page.route('**/api/setting/update', async route => {
        if (route.request().method() === 'OPTIONS') return route.continue()
        const value = route.request().postDataJSON()?.data?.Update?.MirrorChyanCDK
        if (value === olderDraft) {
          const response = await route.fetch()
          olderSaveStarted()
          await olderSaveGate
          return route.fulfill({ response })
        }
        if (value === newerDraft && rejectNextSave) {
          rejectNextSave = false
          return route.fulfill({
            status: 503,
            headers: { 'Access-Control-Allow-Origin': '*' },
            json: { code: 500, status: 'error', message: 'E2E update settings unavailable' },
          })
        }
        return route.continue()
      })

      const olderSaved = settingsResponse(page, 'update')
      const olderRead = settingsResponse(page, 'get')
      await cdk.fill(olderDraft)
      await cdk.blur()
      await olderSaving
      await cdk.fill(newerDraft)
      releaseOlderSave()
      expect((await (await olderSaved).json()).code).toBe(200)
      expect((await (await olderRead).json()).data.Update.MirrorChyanCDK).toBe(olderDraft)
      await expect(cdk).toHaveValue(newerDraft)

      const rejected = settingsResponse(page, 'update')
      await cdk.blur()
      expect((await rejected).status()).toBe(503)
      await expect(page.locator('.ant-message-error')).toContainText(
        'E2E update settings unavailable'
      )
      await expect(cdk).toHaveValue(newerDraft)
      const unchanged = await page.request.post(`${backend}/api/setting/get`)
      expect((await unchanged.json()).data.Update.MirrorChyanCDK).toBe(olderDraft)
      await app.evidence('settings-update-draft-retained', ['.cdk-input input'])

      const retried = settingsResponse(page, 'update')
      const retryRead = settingsResponse(page, 'get')
      await cdk.focus()
      await cdk.blur()
      expect((await (await retried).json()).code).toBe(200)
      expect((await (await retryRead).json()).data.Update.MirrorChyanCDK).toBe(newerDraft)
      const reloaded = settingsResponse(page, 'get')
      await page.reload()
      expect((await (await reloaded).json()).data.Update).toMatchObject({
        Channel: channelValue,
        Source: 'MirrorChyan',
        MirrorChyanCDK: newerDraft,
      })
      await page.getByRole('tab', { name: 'About', exact: true }).click()
      await expect(channel.getByRole('radio', { name: channelLabel, exact: true })).toBeChecked()
      await expect(source.getByRole('radio', { name: /^MirrorChyan/ })).toBeChecked()
      await expect(cdk).toHaveValue(newerDraft)
      await app.evidence('settings-update-reloaded', ['.cdk-input input'])
    } finally {
      releaseOlderSave()
      await page.unroute('**/api/setting/update')
      const restored = await page.request.post(`${backend}/api/setting/update`, {
        data: { data: { Update: original } },
      })
      expect((await restored.json()).code).toBe(200)
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
    await expect(page.locator('.settings-navigation-toggle')).toHaveCount(0)
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
    const panel = page.locator('.settings-navigation-panel')
    const toggle = page.locator('.settings-navigation-toggle')
    const restore = async () => {
      await expect(toggle).toHaveAttribute('aria-busy', 'false')
      if ((await toggle.getAttribute('aria-expanded')) === 'false') await toggle.click()
    }
    await expect(navigation).toBeVisible()
    await expect(panel.getByRole('button', { name: 'Hide section navigation' })).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const expanded = (await toggle.boundingBox())!
    const links = (await navigation.boundingBox())!
    expect(links.y - expanded.y - expanded.height).toBeGreaterThanOrEqual(0)
    expect(links.y - expanded.y - expanded.height).toBeLessThanOrEqual(16)
    await expect(page.locator('.settings-shell-header').getByRole('button')).toHaveCount(0)
    await app.evidence('settings-navigation-expanded')
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
      await expect(toggle).toHaveAttribute('aria-expanded', 'false')
      await expect(navigation).toHaveCount(0)
      await expect(layout).toHaveAttribute('data-effective-layout', 'dual')
      await expect(toggle).toBeFocused()
      const collapsed = (await toggle.boundingBox())!
      expect(collapsed.x).toBeCloseTo(expanded.x, 0)
      expect(collapsed.y).toBeCloseTo(expanded.y, 0)
      const content = (await layout.locator('.ant-tabs-content-holder').boundingBox())!
      expect(content.x + content.width).toBeLessThanOrEqual(collapsed.x)
      await app.evidence('settings-navigation-collapsed')
      await page.setViewportSize({ width: 1040, height: 900 })
      await expect(navigation).toHaveCount(0)
      await expect(layout).toHaveAttribute('data-effective-layout', 'single')

      // 偏好跨重载保留
      await page.reload()
      await expect(toggle).toHaveAttribute('aria-expanded', 'false')
      await expect(navigation).toHaveCount(0)
      await page.setViewportSize({ width: 1920, height: 1080 })
      await expect(toggle).toHaveAttribute('aria-expanded', 'false')
      await expect(navigation).toHaveCount(0)
      await app.evidence('settings-navigation-hidden')

      await restore()
      await expect(navigation).toBeVisible()
      await page.reload()
      await expect(toggle).toHaveAttribute('aria-expanded', 'true')
      await expect(navigation).toBeVisible()
      await toggle.focus()
      await page.keyboard.press('Enter')
      await expect(toggle).toHaveAttribute('aria-expanded', 'false')
      await expect(toggle).toHaveAttribute('aria-busy', 'false')
      await page.keyboard.press('Enter')
      await expect(toggle).toHaveAttribute('aria-expanded', 'true')
      await expect(navigation).toBeVisible()
      await expect(toggle).toHaveAttribute('aria-busy', 'false')
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
