import type { APIRequestContext, Locator, Page } from '@playwright/test'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

const post = async (request: APIRequestContext, path: string, data: unknown) => {
  const response = await request.post(`${backend}${path}`, { data })
  expect(response.ok()).toBe(true)
  const body = await response.json()
  expect(body.code).toBe(200)
  return body
}

const textGeometry = (group: Locator) =>
  group.locator('.config-mode-option').evaluateAll(cards =>
    cards.map(card => {
      const bounds = card.getBoundingClientRect()
      const copy = card.querySelector('.config-mode-copy')!
      const copyBounds = copy.getBoundingClientRect()
      const outside: string[] = []
      for (const text of card.querySelectorAll(
        '.config-mode-title, .config-mode-description, .config-mode-summary, .config-mode-disabled-reason'
      )) {
        if (!text.getClientRects().length) continue
        const range = document.createRange()
        range.selectNodeContents(text)
        if (
          [...range.getClientRects()].some(
            rect =>
              rect.left < copyBounds.left - 1 ||
              rect.right > copyBounds.right + 1 ||
              rect.left < bounds.left - 1 ||
              rect.right > bounds.right + 1 ||
              rect.top < bounds.top - 1 ||
              rect.bottom > bounds.bottom + 1
          )
        )
          outside.push(text.textContent?.trim() ?? '')
      }
      return { copyWidth: copyBounds.width, outside }
    })
  )

const expectReadableCards = async (group: Locator, count: number, minimumTextWidth = 100) => {
  const geometry = await textGeometry(group)
  expect.soft(geometry.length).toBe(count)
  expect
    .soft(
      geometry.flatMap(card => card.outside),
      'Text stays inside its own card'
    )
    .toEqual([])
  expect
    .soft(Math.min(...geometry.map(card => card.copyWidth)), 'Readable text column')
    .toBeGreaterThanOrEqual(minimumTextWidth)
}

const visibleDescriptions = (group: Locator) =>
  group
    .locator('.config-mode-description')
    .evaluateAll(elements => elements.map(element => element.getClientRects().length > 0))

const expectCompactCards = async (group: Locator, count: number) => {
  const boxes = await group.locator('.config-mode-option').evaluateAll(elements =>
    elements.map(element => {
      const box = element.getBoundingClientRect()
      return { left: box.left, right: box.right, top: box.top, bottom: box.bottom }
    })
  )
  expect
    .soft(
      boxes.every(
        (box, index) =>
          Math.abs(box.left - boxes[0]!.left) <= 1 &&
          Math.abs(box.right - boxes[0]!.right) <= 1 &&
          (index === 0 || box.top >= boxes[index - 1]!.bottom)
      ),
      'Narrow options form one vertical column without overlap'
    )
    .toBe(true)
  expect
    .soft(await visibleDescriptions(group), 'Long card descriptions collapse')
    .toEqual(Array.from({ length: count }, () => false))
  const summaries = group.locator('.config-mode-summary')
  expect.soft(await summaries.count(), 'Every option retains its key distinction').toBe(count)
  expect
    .soft(
      await summaries.evaluateAll(elements =>
        elements.every(
          element => element.getClientRects().length > 0 && Boolean(element.textContent?.trim())
        )
      )
    )
    .toBe(true)
}

const checkDisclosure = async (
  page: Page,
  group: Locator,
  count: number,
  evidence?: () => Promise<void>
) => {
  const container = group.locator('..')
  const toggle = container.locator('.config-mode-details-toggle')
  expect.soft(await toggle.count(), 'A keyboard-operable description control is available').toBe(1)
  if ((await toggle.count()) !== 1) return

  const panel = container.locator('.config-mode-details')
  const before = await group.locator('input[type="radio"]').evaluateAll(inputs =>
    inputs.map(input => ({
      checked: (input as HTMLInputElement).checked,
      disabled: (input as HTMLInputElement).disabled,
    }))
  )
  const updates: string[] = []
  const observeUpdate = (request: import('@playwright/test').Request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/scripts/user/update')) {
      updates.push(request.postData() ?? '')
    }
  }
  page.on('request', observeUpdate)
  try {
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(toggle).toHaveAttribute('aria-controls', (await panel.getAttribute('id')) ?? '')
    await toggle.focus()
    await page.keyboard.press('Enter')
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await expect(panel).toBeVisible()
    await expect(panel.locator('dd')).toHaveCount(count)
    expect
      .soft(await panel.locator('dd').allTextContents())
      .toEqual(await group.locator('.config-mode-description').allTextContents())
    const outside = await panel.evaluate(container => {
      const bounds = container.getBoundingClientRect()
      return [...container.querySelectorAll('dt, dd')]
        .filter(text => {
          const range = document.createRange()
          range.selectNodeContents(text)
          return [...range.getClientRects()].some(
            rect =>
              rect.left < bounds.left - 1 ||
              rect.right > bounds.right + 1 ||
              rect.top < bounds.top - 1 ||
              rect.bottom > bounds.bottom + 1
          )
        })
        .map(text => text.textContent?.trim())
    })
    expect.soft(outside, 'Expanded descriptions stay inside the detail panel').toEqual([])
    if (evidence) await evidence()
    await page.keyboard.press('Space')
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(panel).toBeHidden()
    expect
      .soft(
        await group.locator('input[type="radio"]').evaluateAll(inputs =>
          inputs.map(input => ({
            checked: (input as HTMLInputElement).checked,
            disabled: (input as HTMLInputElement).disabled,
          }))
        )
      )
      .toEqual(before)
    expect.soft(updates, 'Reading descriptions does not save account configuration').toEqual([])
  } finally {
    page.off('request', observeUpdate)
  }
}

test.describe('@config-mode-cards', () => {
  test('keeps configuration choices readable and descriptions accessible in narrow containers', async ({
    app,
    page,
  }, testInfo) => {
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 1512, height: 1000 })
    await app.goto('/settings')
    const language = page.locator('.language-select')
    const originalLanguage = await language.locator('.ant-select-selection-item').innerText()
    const theme = page.locator('.theme-mode-control')
    const originalTheme = await theme
      .locator('.ant-segmented-item')
      .evaluateAll(elements =>
        elements.findIndex(element => element.classList.contains('ant-segmented-item-selected'))
      )
    const chooseLanguage = async (label: string) => {
      await language.click()
      await page.locator('.ant-select-dropdown:visible').getByText(label, { exact: true }).click()
      await expect(language.locator('.ant-select-selection-item')).toHaveText(label)
    }
    const scripts: { scriptId: string; userId?: string; type: string; route: string }[] = []
    try {
      for (const item of [
        { type: 'General', route: 'general' },
        { type: 'MaaEnd', route: 'maaend' },
        { type: 'Whimbox', route: 'whimbox' },
      ]) {
        const { scriptId } = await post(page.request, '/api/scripts/add', { type: item.type })
        const script = {
          ...item,
          scriptId: scriptId as string,
          userId: undefined as string | undefined,
        }
        scripts.push(script)
        await post(page.request, '/api/scripts/update', {
          scriptId,
          data: { Info: { Name: `Compact ${item.type}` } },
        })
        script.userId = (await post(page.request, '/api/scripts/user/add', { scriptId })).userId
        await post(page.request, '/api/scripts/user/update', {
          scriptId,
          userId: script.userId,
          data: { Info: { Base: 'independent', Name: `Compact ${item.type} account` } },
        })
      }
      const general = scripts[0]!
      const generalRoute = `/scripts/${general.scriptId}/users/${general.userId}/edit/general`
      for (const scenario of [
        { language: 'English', key: 'en-light', dark: false },
        { language: '简体中文', key: 'zh-light', dark: false },
        { language: '日本語', key: 'ja-dark', dark: true },
      ]) {
        await page.setViewportSize({ width: 1512, height: 1000 })
        await app.goto('/settings')
        await theme
          .locator('.ant-segmented-item')
          .nth(scenario.dark ? 2 : 1)
          .click()
        if (scenario.dark) await expect(page.locator('html')).toHaveClass(/dark/)
        else await expect(page.locator('html')).not.toHaveClass(/dark/)
        await chooseLanguage(scenario.language)
        await app.goto(generalRoute)
        const group = page.locator('.config-mode-options').first()
        const cards = group.locator('.config-mode-option')
        await expect(cards).toHaveCount(3)
        await expect(cards.nth(1).locator('input')).toBeEnabled()
        await expect(cards.first().locator('input')).toBeDisabled()
        if (scenario.key === 'en-light') {
          await app.evidence('config-mode-general-en-light-wide')
          await expectReadableCards(group, 3)
          expect.soft(await visibleDescriptions(group)).toEqual([true, true, true])
        }
        await page.setViewportSize({ width: 768, height: 1000 })
        await app.evidence(`config-mode-general-${scenario.key}-narrow`)
        await testInfo.attach(`geometry-${scenario.key}`, {
          body: JSON.stringify(await textGeometry(group)),
          contentType: 'application/json',
        })
        await expectReadableCards(group, 3)
        await expectCompactCards(group, 3)
        const reason = cards.first().locator('.config-mode-disabled-reason')
        expect
          .soft(await reason.count(), 'The unavailable choice keeps its explanation visible')
          .toBe(1)
        if (await reason.count()) await expect(reason).toBeVisible()
        await checkDisclosure(
          page,
          group,
          3,
          scenario.key === 'en-light'
            ? () => app.evidence('config-mode-general-en-light-descriptions-expanded')
            : undefined
        )
        if (scenario.key === 'en-light') {
          await page.setViewportSize({ width: 480, height: 1000 })
          await app.evidence('config-mode-general-en-light-minimum')
          await expectReadableCards(group, 3, 1)
          await expectCompactCards(group, 3)
          await checkDisclosure(page, group, 3)
          await page.setViewportSize({ width: 640, height: 1000 })
          await expectReadableCards(group, 3)
          await expectCompactCards(group, 3)
        }
      }

      const group = page.locator('.config-mode-options').first()
      const saved = page.waitForResponse(
        response =>
          response.url().endsWith('/api/scripts/user/update') &&
          response.request().postDataJSON()?.data?.Info?.Base === 'native'
      )
      await group.locator('.config-mode-option').last().click()
      expect((await (await saved).json()).code).toBe(200)
      await page.reload()
      await expect(group.locator('.config-mode-option').last().locator('input')).toBeChecked()
      await expect(group.locator('.config-mode-option').first().locator('input')).toBeDisabled()
      await expect(group.locator('.config-mode-option').first().locator('input')).not.toBeChecked()

      await page.setViewportSize({ width: 1512, height: 1000 })
      await app.goto('/settings')
      await chooseLanguage('English')
      const maaEnd = scripts[1]!
      await app.goto(`/scripts/${maaEnd.scriptId}/users/${maaEnd.userId}/edit/maaend`)
      const groups = page.locator('.config-mode-options')
      await expect(groups).toHaveCount(2)
      await expect(
        groups.first().locator('.config-mode-option').nth(1).locator('input')
      ).toBeChecked()
      await expect(
        groups.first().locator('.config-mode-option').nth(1).locator('input')
      ).toBeEnabled()
      await app.evidence('config-mode-maaend-en-dark-wide')
      for (const [index, count] of [3, 2].entries()) {
        await expectReadableCards(groups.nth(index), count)
        expect
          .soft(await visibleDescriptions(groups.nth(index)))
          .toEqual(Array.from({ length: count }, () => true))
      }
      await page.setViewportSize({ width: 768, height: 1000 })
      await app.evidence('config-mode-maaend-en-dark-narrow')
      for (const [index, count] of [3, 2].entries()) {
        const current = groups.nth(index)
        await expectReadableCards(current, count)
        await expectCompactCards(current, count)
        await checkDisclosure(
          page,
          current,
          count,
          index === 1
            ? () => app.evidence('config-mode-maaend-en-dark-overlay-descriptions-expanded')
            : undefined
        )
      }
      const summaries = groups.nth(1).locator('.config-mode-summary')
      if ((await summaries.count()) === 2) {
        expect
          .soft(await summaries.allTextContents())
          .toEqual(['Override for tasks, then restore', 'Keep base settings'])
      }

      const whimbox = scripts[2]!
      await app.goto(`/scripts/${whimbox.scriptId}/users/${whimbox.userId}/edit/whimbox`)
      const whimboxGroup = page.locator('.config-mode-options').first()
      const whimboxCards = whimboxGroup.locator('.config-mode-option')
      await expect(whimboxCards).toHaveCount(3)
      await expect(whimboxCards.nth(1).locator('input')).toBeChecked()
      await expect(whimboxCards.first().locator('input')).toBeEnabled()
      await expect(whimboxCards.nth(1)).toHaveClass(/selected/)
      await expect(page.locator('.user-edit-content input.ant-input').first()).toHaveValue(
        'Compact Whimbox account'
      )
      await whimboxCards.evaluateAll(cards =>
        Promise.all(
          cards.flatMap(card => card.getAnimations().map(animation => animation.finished))
        )
      )
      await app.evidence('config-mode-whimbox-en-dark-narrow')
      await expectReadableCards(whimboxGroup, 3)
      await expectCompactCards(whimboxGroup, 3)
      expect
        .soft(await whimboxCards.first().locator('.config-mode-summary').allTextContents())
        .toEqual(['Only this account'])
      await checkDisclosure(page, whimboxGroup, 3)
    } finally {
      await page.setViewportSize({ width: 1512, height: 1000 })
      await app.goto('/settings')
      await chooseLanguage(originalLanguage)
      await theme.locator('.ant-segmented-item').nth(originalTheme).click()
      for (const script of scripts.reverse()) {
        if (script.userId)
          await post(page.request, '/api/scripts/user/delete', {
            scriptId: script.scriptId,
            userId: script.userId,
          })
        await post(page.request, '/api/scripts/delete', { scriptId: script.scriptId })
      }
    }
  })
})
