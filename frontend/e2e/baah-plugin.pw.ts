import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { expect, test } from './fixtures'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test('@account-editors @baah edits the migrated account and restores its native config', async ({
  app,
  page,
}) => {
  const post = async (endpoint: string, data: object) => {
    const response = await page.request.post(backend + endpoint, { data })
    const body = await response.json()
    expect(body.code, body.message).toBe(200)
    return body
  }
  const installation = await mkdtemp(path.join(tmpdir(), 'mas-baah-'))
  const native = path.join(installation, 'BAAH_CONFIGS')
  const exe = path.join(installation, 'BAAH.exe')
  const original = { profile: 'initial-native-config' }
  const { scriptId } = await post('/api/scripts/add', { type: 'BAAH' })
  try {
    await mkdir(native)
    await writeFile(exe, '')
    await writeFile(path.join(native, 'existing.json'), JSON.stringify(original))
    await post('/api/scripts/update', { scriptId, data: { Script: { BAAHPath: exe } } })
    const { userId } = await post('/api/scripts/user/add', { scriptId })
    await post('/api/scripts/user/update', {
      scriptId,
      userId,
      data: { Info: { ConfigName: 'existing' } },
    })
    const account = async () =>
      (await post('/api/scripts/user/get', { scriptId, userId })).data[userId]
    const userDetail = await post('/api/scripts/user/get', { scriptId, userId })
    expect(userDetail.ui.backupTargets).toEqual([
      { key: 'mas', kind: 'user', editorEvents: ['leave'] },
      { key: 'native', kind: 'script', editorEvents: ['enter'] },
    ])
    await page.goto(`/#/scripts/${scriptId}/edit/baah`)
    await expect(page).toHaveURL(/\/edit\/plugin\/BAAH$/)
    const cdk = page.locator('.declarative-field[aria-label="MirrorChyan CDK"] input')
    await expect(cdk).toBeDisabled()
    await page
      .locator('.declarative-field[aria-label="Take over updates"]')
      .getByRole('switch')
      .click()
    await expect(cdk).toBeEnabled()
    await expect(cdk).toHaveAttribute('type', 'password')
    const cdkSaved = page.waitForResponse(response => {
      const request = response.request()
      return (
        new URL(response.url()).pathname === '/api/scripts/update' &&
        request.method() === 'POST' &&
        request.postDataJSON()?.data?.Update?.MirrorChyanCDK === 'e2e-placeholder'
      )
    })
    await cdk.fill('e2e-placeholder')
    await cdk.blur()
    expect((await (await cdkSaved).json()).code).toBe(200)
    await page.reload()
    await expect(cdk).toBeEnabled()
    await expect(cdk).toHaveAttribute('type', 'password')

    const userPath = `/scripts/${scriptId}/users/${userId}/edit`
    await page.goto(`/#${userPath}/baah`)
    await expect(page).toHaveURL(/\/edit\/plugin\/BAAH$/)
    const panel = page.frameLocator('iframe[title="baah_adapter"]')
    const name = panel.getByLabel('Account name', { exact: true })
    const selected = panel.getByLabel('Default config name', { exact: true })
    await expect(selected).toHaveValue('existing')
    await name.fill('BAAH account after migration')
    await name.blur()
    await expect.poll(async () => (await account()).Info.Name).toBe('BAAH account after migration')
    await panel.getByLabel('Enabled', { exact: true }).selectOption('false')
    await expect.poll(async () => (await account()).Info.Status).toBe(false)
    const days = panel.getByLabel('Days left', { exact: true })
    await days.fill('7')
    await days.blur()
    await expect.poll(async () => (await account()).Info.RemainedDay).toBe(7)
    const note = panel.getByLabel('Note', { exact: true })
    await note.fill('Migrated account')
    await note.blur()
    await expect.poll(async () => (await account()).Info.Notes).toBe('Migrated account')
    await panel.getByLabel('Reminder server', { exact: true }).selectOption('Globle')
    await expect.poll(async () => (await account()).Info.ActivityLineType).toBe('Globle')
    await panel.getByRole('button', { name: 'Generate recommended config' }).click()
    const generated = '推荐配置'
    await expect(panel.locator(`#configs option[value="${generated}"]`)).toHaveCount(1)
    await expect(selected).toHaveValue('existing')
    expect((await account()).Info.ConfigName).toBe('existing')
    await selected.fill(generated)
    await selected.blur()
    await expect.poll(async () => (await account()).Info.ConfigName).toBe(generated)

    await page.reload()
    await expect(page).toHaveURL(new RegExp(userPath + '/plugin/BAAH$'))
    await expect(name).toHaveValue('BAAH account after migration')
    await expect(selected).toHaveValue(generated)
    await expect(days).toHaveValue('7')
    await expect(note).toHaveValue('Migrated account')
    await page.getByRole('button', { name: 'Config restore', exact: true }).click()
    const modal = page.getByRole('dialog', { name: 'Config restore' })
    await modal.getByText('Restore BAAH native config', { exact: true }).click()
    // The oldest native snapshot belongs to the initial binding. Restoring it writes the selected file.
    await modal.getByRole('button', { name: 'Restore', exact: true }).last().click()
    const restored = page.waitForResponse(
      response =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === '/api/scripts/backup/restore'
    )
    await page
      .getByRole('dialog')
      .filter({ hasText: 'Overwrite current config' })
      .getByRole('button', { name: 'Restore', exact: true })
      .click()
    expect((await (await restored).json()).code).toBe(200)
    expect(JSON.parse(await readFile(path.join(native, generated + '.json'), 'utf8'))).toEqual(
      original
    )
    await app.evidence('baah-account-native-restore')
    const archived = page.waitForResponse(response => {
      const request = response.request()
      return (
        new URL(response.url()).pathname === '/api/scripts/backup/ensure' &&
        request.method() === 'POST' &&
        request.postDataJSON()?.target === 'mas'
      )
    })
    await app.goto('/scripts')
    expect((await (await archived).json()).code).toBe(200)
  } finally {
    await app.goto('/scripts')
    await post('/api/scripts/delete', { scriptId })
    await rm(installation, { recursive: true, force: true })
  }
})
