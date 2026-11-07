import type { Locator, Page } from '@playwright/test'
import type { InstalledAppearance } from '../src/types/appearance'
import type { ElectronAPI } from '../src/types/electron'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

const resolveColor = (page: Page, color: string) =>
  page.evaluate(color => {
    const reference = document.createElement('span')
    reference.style.color = color
    document.body.append(reference)
    const resolved = getComputedStyle(reference).color
    reference.remove()
    return resolved
  }, color)

const post = async (page: Page, path: string, data: unknown) => {
  const response = await page.request.post(`${backend}${path}`, { data })
  expect(response.ok()).toBe(true)
  const body = await response.json()
  expect(body.code).toBe(200)
  return body
}

const expectContentDividers = async (locator: Locator, color: string) => {
  const styles = await locator.evaluateAll(elements =>
    elements.map(element => {
      const style = getComputedStyle(element)
      return { color: style.borderBottomColor, visible: style.borderBottomWidth !== '0px' }
    })
  )
  expect.soft(styles.length, locator.toString()).toBeGreaterThan(0)
  expect.soft(styles, locator.toString()).toEqual(styles.map(() => ({ color, visible: true })))
}

test.describe('@settings @shared-form-styles', () => {
  test('shares content dividers across settings, editors and scheduler in both themes', async ({
    app,
    page,
  }) => {
    await page.setViewportSize({ width: 1512, height: 1000 })
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    await app.goto('/settings')
    const theme = page.locator('.theme-mode-control')
    await expect(theme).toBeVisible()
    const originalTheme = await theme.locator('.ant-segmented-item-selected').innerText()
    const { scriptId } = await post(page, '/api/scripts/add', { type: 'General' })
    let userId: string | undefined
    try {
      await post(page, '/api/scripts/update', {
        scriptId,
        data: { Info: { Name: 'Shared form styles' } },
      })
      userId = (await post(page, '/api/scripts/user/add', { scriptId })).userId
      for (const mode of ['light', 'dark'] as const) {
        await page.setViewportSize({ width: 1512, height: 1000 })
        await app.goto('/settings')
        const label = mode === 'light' ? 'Light' : 'Dark'
        await theme.getByText(label, { exact: true }).click()
        await expect(theme.getByRole('radio', { name: label, exact: true })).toBeChecked()
        if (mode === 'light') await expect(page.locator('html')).not.toHaveClass(/dark/)
        else await expect(page.locator('html')).toHaveClass(/dark/)
        await expect(page.locator('html')).not.toHaveClass(/theme-transition/)
        const dividerColor = await resolveColor(page, 'var(--ant-color-border-secondary)')

        const pane = page.locator('.ant-tabs-tabpane-active')
        const rows = pane.locator('.ui-section-card-body > .ui-row:not(:last-child)')
        await expect(rows.first()).toBeVisible()
        await app.evidence(`shared-form-settings-${mode}`)
        if (mode === 'light') {
          expect.soft(dividerColor).toBe('rgb(224, 224, 224)')
          await expect
            .soft(page.locator('body'))
            .toHaveCSS('background-color', 'rgb(233, 233, 233)')
          await expect
            .soft(pane.locator('.ui-section-card').first())
            .toHaveCSS('background-color', 'rgb(242, 242, 242)')
        }
        await expectContentDividers(rows, dividerColor)
        const unlined = pane.locator(
          '.ui-section-card > .section-header, .ui-section-card-body > .ui-row:last-child'
        )
        const widths = await unlined.evaluateAll(elements =>
          elements.map(element => getComputedStyle(element).borderBottomWidth)
        )
        expect
          .soft(widths, 'SectionCard titles and final setting rows stay unlined')
          .toEqual(widths.map(() => '0px'))

        await app.goto(`/scripts/${scriptId}/edit/general`)
        const scriptHeaders = page.locator('.script-edit-content .form-section > .section-header')
        await expect(scriptHeaders.first()).toBeVisible()
        await page
          .locator('.script-edit-content .form-section')
          .evaluateAll(sections =>
            Promise.all(
              sections.flatMap(section =>
                section.getAnimations().map(animation => animation.finished)
              )
            )
          )
        await app.evidence(`shared-form-script-${mode}`)
        await expectContentDividers(scriptHeaders, dividerColor)

        await app.goto(`/scripts/${scriptId}/users/${userId}/edit/general`)
        const userHeaders = page.locator('.user-edit-content .form-section > .section-header')
        await expect(userHeaders.first()).toBeVisible()
        await app.evidence(`shared-form-user-${mode}`)
        await expectContentDividers(userHeaders, dividerColor)

        await app.goto('/scheduler')
        const panelHeaders = page.locator('.scheduler-panel-header')
        await expect(panelHeaders).toHaveCount(2)
        await expect(panelHeaders.first()).toBeVisible()
        await app.evidence(`shared-form-scheduler-${mode}`)
        await expectContentDividers(panelHeaders, dividerColor)

        await page.setViewportSize({ width: 768, height: 1000 })
        await app.goto('/settings')
        await expect(rows.first()).toBeVisible()
        await app.evidence(`shared-form-settings-${mode}-narrow`)
        const settingsOverflow = await page
          .locator('.content-area, .settings-content, .ant-tabs-tabpane-active')
          .evaluateAll(elements =>
            elements.map(element => element.scrollWidth - element.clientWidth)
          )
        expect
          .soft(Math.max(...settingsOverflow), 'Narrow settings content fits horizontally')
          .toBeLessThanOrEqual(1)

        await app.goto(`/scripts/${scriptId}/users/${userId}/edit/general`)
        await expect(userHeaders.first()).toBeVisible()
        await app.evidence(`shared-form-user-${mode}-narrow`)
        const userOverflow = await page
          .locator('.content-area, .user-edit-content, .user-edit-content .ant-card-body')
          .evaluateAll(elements =>
            elements.map(element => element.scrollWidth - element.clientWidth)
          )
        expect
          .soft(Math.max(...userOverflow), 'Narrow user content fits horizontally')
          .toBeLessThanOrEqual(1)
        await expect
          .soft(page.locator('.user-edit-content .config-card > .ant-card-body'))
          .toHaveCSS('padding', '32px')
      }
    } finally {
      await app.goto('/settings')
      await theme.getByText(originalTheme, { exact: true }).click()
      await expect(theme.getByRole('radio', { name: originalTheme, exact: true })).toBeChecked()
      if (userId) await post(page, '/api/scripts/user/delete', { scriptId, userId })
      await post(page, '/api/scripts/delete', { scriptId })
    }
  })

  test('preserves appearance background, translucent surfaces and divider overrides', async ({
    app,
    page,
  }) => {
    const appearances: InstalledAppearance[] = (['light', 'dark'] as const).map(mode => ({
      formatVersion: 1,
      id: `shared-form-${mode}`,
      name: `Shared form ${mode}`,
      mode,
      tokens: {
        colorPrimary: '#1677ff',
        colorBgContainer: mode === 'light' ? '#f2e8dc' : '#243040',
        colorBorderSecondary: mode === 'light' ? '#987654' : '#a4b5c6',
      },
      background: { path: 'assets/background.png', opacity: 0.75, surfaceOpacity: 0.5 },
      backgroundUrl:
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAX+XDSwAAAABJRU5ErkJggg==',
    }))
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
    await page.setViewportSize({ width: 1512, height: 1000 })
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    await app.goto('/settings')
    const selector = page.locator('.appearance-select')
    const settingsSurface = page.locator('.settings-content')
    const rows = page.locator(
      '.ant-tabs-tabpane-active .ui-section-card-body > .ui-row:not(:last-child)'
    )
    await expect(selector).toBeVisible()
    const builtInBackground = await settingsSurface.evaluate(
      element => getComputedStyle(element).backgroundColor
    )
    const builtInDivider = await resolveColor(page, 'var(--ant-color-border-secondary)')
    const selectAppearance = async (label: string) => {
      await selector.click()
      await page.locator('.ant-select-dropdown:visible').getByText(label, { exact: true }).click()
      await expect(selector.locator('.ant-select-selection-item')).toHaveText(label)
      await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0)
      await expect(page.locator('html')).not.toHaveClass(/theme-transition/)
    }
    const { scriptId } = await post(page, '/api/scripts/add', { type: 'General' })
    let userId: string | undefined
    try {
      userId = (await post(page, '/api/scripts/user/add', { scriptId })).userId
      for (const appearance of appearances) {
        await selectAppearance(appearance.name)
        if (appearance.mode === 'light') await expect(page.locator('html')).not.toHaveClass(/dark/)
        else await expect(page.locator('html')).toHaveClass(/dark/)
        const background = page.locator('.appearance-background')
        await expect(background).toBeVisible()
        await expect(background).toHaveCSS('background-image', /^url\("blob:/)
        await expect(background).toHaveCSS('opacity', '0.75')
        const dividerColor =
          appearance.mode === 'light' ? 'rgb(152, 118, 84)' : 'rgb(164, 181, 198)'
        const surfaceColor = await resolveColor(
          page,
          `color-mix(in srgb, ${appearance.tokens.colorBgContainer} 50%, transparent)`
        )
        await app.evidence(`shared-form-appearance-settings-${appearance.mode}`)
        await expect.soft(settingsSurface).toHaveCSS('background-color', surfaceColor)
        await expect
          .soft(page.locator('.ant-tabs-tabpane-active .ui-section-card').first())
          .toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
        await expectContentDividers(rows, dividerColor)

        await app.goto(`/scripts/${scriptId}/users/${userId}/edit/general`)
        const userHeaders = page.locator('.user-edit-content .form-section > .section-header')
        await expect(userHeaders.first()).toBeVisible()
        await app.evidence(`shared-form-appearance-user-${appearance.mode}`)
        await expect
          .soft(page.locator('.user-edit-content .config-card'))
          .toHaveCSS('background-color', surfaceColor)
        await expect
          .soft(page.locator('.user-edit-content .config-card > .ant-card-body'))
          .toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
        await expectContentDividers(userHeaders, dividerColor)

        await app.goto('/settings')
        await selectAppearance('Default appearance')
        await expect(page.locator('.appearance-background')).toHaveCount(0)
        await expect.soft(settingsSurface).toHaveCSS('background-color', builtInBackground)
        await expectContentDividers(rows, builtInDivider)
      }
      await app.evidence('shared-form-appearance-default-restored')
    } finally {
      await app.goto('/settings')
      await selectAppearance('Default appearance')
      if (userId) await post(page, '/api/scripts/user/delete', { scriptId, userId })
      await post(page, '/api/scripts/delete', { scriptId })
    }
  })
})
