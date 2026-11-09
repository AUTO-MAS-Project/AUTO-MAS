import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@script-navigation', () => {
  test('creates a general script and reaches its script and account editors from the list', async ({
    app,
    page,
  }) => {
    const responseFor = (path: string) =>
      page.waitForResponse(
        response =>
          response.request().method() === 'POST' && new URL(response.url()).pathname === path
      )
    const scriptName = 'Navigation general script'
    const accountName = 'Navigation account'
    const note = 'Saved through the account editor'
    let scriptId: string | undefined

    try {
      await app.goto('/scripts')
      await page.getByRole('button', { name: /New managed script$/ }).click()
      const dialog = page.getByRole('dialog', { name: /New managed script$/ })
      await dialog.getByRole('radio', { name: /^General / }).check()
      await dialog.getByRole('button', { name: /Next$/ }).click()
      await dialog.getByText('Custom configuration', { exact: true }).click()
      const creating = responseFor('/api/scripts/add')
      await dialog.getByRole('button', { name: /Create and configure$/ }).click()
      const createdResponse = await creating
      expect(createdResponse.request().postDataJSON()).toMatchObject({ type: 'General' })
      const created = await createdResponse.json()
      expect(created.code).toBe(200)
      scriptId = created.scriptId
      expect(scriptId).toBeTruthy()
      await expect(page).toHaveURL(new RegExp(`#/scripts/${scriptId}/edit/general$`))
      const scriptNameInput = page.getByPlaceholder('Enter a managed script name', { exact: true })
      await expect(scriptNameInput).toBeEnabled()
      await scriptNameInput.fill(scriptName)
      const renaming = responseFor('/api/scripts/update')
      await scriptNameInput.blur()
      expect((await (await renaming).json()).code).toBe(200)

      await page.locator('.script-edit-header').getByRole('button', { name: /Back$/ }).click()
      await expect(page).toHaveURL(/#\/scripts$/)
      const card = page.locator('.script-card').filter({
        has: page.getByRole('heading', { name: scriptName, exact: true }),
      })
      await expect(card).toBeVisible()
      await card.getByRole('button', { name: /Edit managed script$/ }).click()
      await expect(page).toHaveURL(new RegExp(`#/scripts/${scriptId}/edit/general$`))
      await expect(scriptNameInput).toHaveValue(scriptName)
      await page.locator('.script-edit-header').getByRole('button', { name: /Back$/ }).click()

      const addingAccount = responseFor('/api/scripts/user/add')
      await card.getByRole('button', { name: /Add an account$/ }).click()
      await expect(page).toHaveURL(new RegExp(`#/scripts/${scriptId}/users/add/general$`))
      const account = await (await addingAccount).json()
      expect(account.code).toBe(200)
      const userId: string = account.userId
      expect(userId).toBeTruthy()
      const accountNameInput = page.getByPlaceholder('Enter the account name', { exact: true })
      await expect(accountNameInput).toBeEnabled()
      await accountNameInput.fill(accountName)
      const namingAccount = responseFor('/api/scripts/user/update')
      await accountNameInput.blur()
      expect((await (await namingAccount).json()).code).toBe(200)

      await page.locator('.user-edit-header').getByRole('button', { name: /Back$/ }).click()
      await expect(page).toHaveURL(/#\/scripts$/)
      const row = card.locator('.user-item').filter({
        has: page.getByText(accountName, { exact: true }),
      })
      await expect(row).toBeVisible()
      await row.getByRole('button', { name: /Edit$/ }).click()
      await expect(page).toHaveURL(
        new RegExp(`#/scripts/${scriptId}/users/${userId}/edit/general$`)
      )
      await expect(accountNameInput).toHaveValue(accountName)
      const notes = page.getByPlaceholder('Enter a note', { exact: true })
      await notes.fill(note)
      const savingNote = responseFor('/api/scripts/user/update')
      await notes.blur()
      expect((await (await savingNote).json()).code).toBe(200)
      await page.reload()
      await expect(accountNameInput).toHaveValue(accountName)
      await expect(notes).toHaveValue(note)
      await app.evidence('script-account-navigation')
    } finally {
      if (scriptId) {
        await app.goto('/scripts')
        const response = await page.request.post(`${backend}/api/scripts/delete`, {
          data: { scriptId },
        })
        expect((await response.json()).code).toBe(200)
      }
    }
  })
})
