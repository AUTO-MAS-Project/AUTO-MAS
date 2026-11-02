import type { Page } from '@playwright/test'
import type { I18nMessagesOut } from '../src/api/models/I18nMessagesOut'
import { expect, test } from './fixtures'

const languageSelect = (page: Page) =>
  page
    .locator('.form-item-vertical')
    .filter({ has: page.locator('.form-label').filter({ hasText: /^(Language|语言|言語)$/ }) })
    .locator('.ant-select')

const chooseLanguage = async (page: Page, name: string) => {
  await languageSelect(page).click()
  await page.locator('.ant-select-dropdown:visible').getByText(name, { exact: true }).click()
}

const menu = (page: Page, name: string) =>
  page.getByRole('menuitem').filter({ has: page.getByText(name, { exact: true }) })

const expectLanguage = async (page: Page, option: string, settings: string) => {
  await expect(languageSelect(page).locator('.ant-select-selection-item')).toHaveText(option)
  await expect(menu(page, settings)).toBeVisible()
  await expect(page.locator('.settings-container')).not.toContainText(
    /core\.common\.language|bootstrap\.locale\./
  )
}

test.describe('@i18n language resources', () => {
  test('switches all languages through settings and retains the choice after navigation and reload', async ({
    app,
    page,
  }) => {
    await app.goto('/settings')
    await expectLanguage(page, 'English', 'Settings')

    for (const language of [
      { option: '简体中文', settings: '设置', home: '主页' },
      { option: '日本語', settings: '設定', home: 'ホーム' },
      { option: 'English', settings: 'Settings', home: 'Home' },
    ]) {
      await chooseLanguage(page, language.option)
      await expectLanguage(page, language.option, language.settings)
      await menu(page, language.home).click()
      await expect(page.locator('.home-title')).toBeVisible()
      await menu(page, language.settings).click()
      await expectLanguage(page, language.option, language.settings)
      await page.reload()
      await expectLanguage(page, language.option, language.settings)
    }
    await app.evidence('i18n-language-reloaded')
  })

  for (const failure of [
    { name: 'catalog business rejection', route: '**/api/i18n/locales', status: 200 },
    { name: 'messages HTTP failure', route: '**/api/i18n/messages?*', status: 503 },
  ]) {
    test(`retries initial resource loading after ${failure.name}`, async ({ app, page }) => {
      await page.route(failure.route, route =>
        route.fulfill({
          status: failure.status,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 500,
            status: 'error',
            message: 'E2E translations unavailable',
          }),
        })
      )
      try {
        await app.goto('/home')
        const gate = page.locator('.i18n-resource-gate')
        await expect(gate.getByRole('alert')).toContainText('Could not load interface translations')
        await expect(gate).toContainText('E2E translations unavailable')
        await expect(page.locator('.home-title')).toHaveCount(0)
        await expect(gate.getByRole('combobox')).toBeVisible()
        await app.evidence(`i18n-${failure.status}-retry`)

        await page.unroute(failure.route)
        await gate.getByRole('button', { name: 'Retry', exact: true }).click()
        await expect(gate).toBeHidden()
        await expect(page.locator('.home-title')).toBeVisible()
        await menu(page, 'Settings').click()
        await expectLanguage(page, 'English', 'Settings')
      } finally {
        await page.unroute(failure.route)
      }
    })
  }

  for (const failure of ['HTTP failure', 'revision mismatch'] as const) {
    test(`keeps the current language after ${failure} and allows switching again`, async ({
      app,
      page,
    }) => {
      await app.goto('/settings')
      await expectLanguage(page, 'English', 'Settings')
      const routePattern = '**/api/i18n/messages?*'
      let rejected = 0
      await page.route(routePattern, async route => {
        if (new URL(route.request().url()).searchParams.get('locale') !== 'ja-JP') {
          return route.continue()
        }
        rejected++
        if (failure === 'HTTP failure') {
          return route.fulfill({ status: 503, body: 'E2E translations unavailable' })
        }
        const response = await route.fetch()
        const body: I18nMessagesOut = await response.json()
        // 保留真实词表，只破坏公开的批次版本，验证前端拒绝混合快照。
        await route.fulfill({
          response,
          json: { ...body, data: { ...body.data, revision: 'e2e-inconsistent-revision' } },
        })
      })
      try {
        await chooseLanguage(page, '日本語')
        await expect(page.locator('.ant-message-error')).toContainText(
          'Could not load the selected language'
        )
        expect(rejected).toBeGreaterThan(0)
        await expectLanguage(page, 'English', 'Settings')
        await page.reload()
        await expectLanguage(page, 'English', 'Settings')

        await page.unroute(routePattern)
        await chooseLanguage(page, '日本語')
        await expectLanguage(page, '日本語', '設定')
        await page.reload()
        await expectLanguage(page, '日本語', '設定')
        await app.evidence(`i18n-${failure.replaceAll(' ', '-')}-recovered`)
      } finally {
        await page.unroute(routePattern)
      }
    })
  }
})
