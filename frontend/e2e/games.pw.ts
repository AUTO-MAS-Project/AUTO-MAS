import { expect, test } from './fixtures'
import { writeFile } from 'node:fs/promises'
import type { GameGetOut } from '../src/api/models/GameGetOut'
import { TriggerUiState } from '../src/api/models/TriggerUiState'

// 用户通过游戏页签登记连接后必须可刷新回读；这里不启动作者机器上的模拟器。
test.describe('@games game targets', () => {
  test('shows activity on the exact device action and disables competing controls', async ({
    app,
    page,
  }) => {
    const gameId = '46236c77-b64e-4e72-be14-ecaefeb2393c'
    const deviceId = '54b0e3aa-5d95-42cc-905f-2f619491720f'
    const otherId = '20486298-6ca1-4e55-8f91-1fb8b009e7b7'
    const taskId = 'c80cf662-ea2f-40d3-8197-7b9f65dba1cc'
    let active: 'show' | 'hide' | undefined
    function hints(fields: string[], running?: string) {
      return fields.map(field => ({
        field,
        editable: active === undefined,
        state: running === field ? 'busy' : 'idle',
      }))
    }
    await page.route('**/api/games/get', route =>
      route.fulfill({
        json: {
          code: 200,
          order: [{ uid: gameId, type: 'GeneralGame' }],
          data: {
            [gameId]: {
              info: { name: 'Device action fixture' },
              devices: {
                order: [deviceId, otherId].map(uid => ({ uid, type: 'GeneralDevice' })),
                data: {
                  [deviceId]: { info: { name: 'First device', status: 0 } },
                  [otherId]: { info: { name: 'Other device', status: 1 } },
                },
              },
            },
          },
          runtime: {
            [gameId]: {
              actionHints: {
                [gameId]: hints(['refresh', 'create_instance']),
                [deviceId]: hints(['close', 'show', 'hide', 'minimize'], active),
                [otherId]: hints(['open']),
              },
            },
          },
        },
      })
    )
    await page.route('**/api/config/triggers/write', route => {
      const command = route.request().postDataJSON()
      expect(command.configUid).toBe(deviceId)
      expect(command.group).toBe('action')
      expect(command.value).toBe(true)
      expect(['show', 'hide']).toContain(command.field)
      active = command.field
      return route.fulfill({ json: { code: 200, data: taskId } })
    })
    await page.route('**/api/config/triggers/active', route =>
      route.fulfill({ json: { code: 200, data: [] } })
    )
    await page.route('**/api/config/triggers/result', route =>
      route.fulfill({ json: { code: 200, data: { state: active ? 'running' : 'succeeded' } } })
    )

    await app.goto('/games')
    const row = page.getByRole('row').filter({ hasText: 'First device' })
    const show = row.getByRole('button', { name: 'Show', exact: true })
    const close = row.getByRole('button', { name: 'Stop', exact: true })
    const open = page
      .getByRole('row')
      .filter({ hasText: 'Other device' })
      .getByRole('button', {
        name: /Start|Open/,
      })
    const refresh = page.getByRole('button', { name: /Refresh/ })
    await show.click()
    await expect(show).toHaveClass(/ant-btn-loading/)
    await expect(close).toBeDisabled()
    await expect(close).not.toHaveClass(/ant-btn-loading/)
    await expect(open).toBeDisabled()
    await expect(refresh).toBeDisabled()
    await expect(page.getByRole('button', { name: /Add device connection/i })).toBeDisabled()
    await row.getByRole('button', { name: /More/ }).hover()
    const hide = page.getByRole('menuitem', { name: 'Hide', exact: true })
    await expect(hide).toHaveAttribute('aria-disabled', 'true')
    await expect(page.getByRole('menuitem', { name: 'Minimize', exact: true })).toHaveAttribute(
      'aria-disabled',
      'true'
    )

    active = undefined
    await expect(close).toBeEnabled()
    await expect(hide).not.toHaveAttribute('aria-disabled', 'true')
    await hide.click()
    await expect(row.getByRole('button', { name: /\bHide\b/ })).toHaveClass(/ant-btn-loading/)
    await expect(show).not.toHaveClass(/ant-btn-loading/)
    await expect(close).toBeDisabled()
    active = undefined
    await expect(open).toBeEnabled()
  })

  test('creates and edits a generic emulator target through the public UI', async ({
    app,
    page,
  }) => {
    await app.goto('/games')
    await expect(page.getByRole('heading', { name: 'Game management' })).toBeVisible()
    await page.getByRole('button', { name: /Add game target/ }).click()
    const dialog = page.getByRole('dialog')
    await dialog.locator('.ant-select').first().click()
    await page
      .locator('.ant-select-dropdown:visible')
      .getByText('General Emulator Adapter', { exact: true })
      .click()
    await dialog.getByLabel('Name', { exact: true }).fill('Isolated generic emulator')
    await dialog.getByRole('button', { name: 'OK', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    const tab = page.getByRole('tab', { name: 'Isolated generic emulator', exact: true })
    await expect(tab).toBeVisible()
    await page.reload()
    await expect(tab).toBeVisible()
    const panel = page.getByRole('tabpanel')
    await expect(panel.getByRole('heading', { name: 'Devices', exact: true })).toBeVisible()
    const game = await page.request.post(
      `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}/api/games/get`,
      { data: {} }
    )
    const configUid = (await game.json()).order[0].uid
    const taskId = '47b17e9c-e285-4ef7-9002-676643210883'
    let busy = true
    const listOperations = '**/api/config/triggers/active'
    const listGames = '**/api/games/get'
    await page.route(listOperations, route =>
      route.fulfill({
        json: {
          code: 200,
          data: busy
            ? [{ taskId, configUid, group: 'action', field: 'refresh', cancelling: false }]
            : [],
        },
      })
    )
    await page.route(listGames, async route => {
      const response = await route.fetch()
      const payload: GameGetOut = await response.json()
      const hint = payload.runtime?.[configUid]?.actionHints?.[configUid]?.find(
        hint => hint.field === 'refresh'
      )
      expect(hint).toBeDefined()
      if (hint && busy) {
        hint.state = TriggerUiState.BUSY
        hint.editable = false
      }
      await route.fulfill({ headers: { 'Access-Control-Allow-Origin': '*' }, json: payload })
    })
    await app.goto('/settings')
    await app.goto('/games')
    await page.reload()
    const refresh = panel.getByRole('button', { name: /Refresh/i })
    await expect(refresh).toHaveClass(/ant-btn-loading/)
    await page.route('**/api/config/triggers/write', route => {
      expect(route.request().postDataJSON()).toEqual({
        configUid,
        group: 'action',
        field: 'refresh',
        value: false,
      })
      busy = false
      return route.fulfill({ json: { code: 200, data: taskId } })
    })
    await page
      .locator('.operation-alert')
      .getByRole('button', { name: /Cancel/ })
      .click()
    await expect(refresh).not.toHaveClass(/ant-btn-loading/)
    await page.unroute('**/api/config/triggers/write')
    await page.unroute(listOperations)
    await page.unroute(listGames)
    await panel.getByLabel('Name', { exact: true }).fill('Updated generic emulator')
    await panel.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(
      page.getByRole('tab', { name: 'Updated generic emulator', exact: true })
    ).toBeVisible()
    const changedOutsidePage = await page.request.post(
      `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}/api/games/update`,
      { data: { gameId: configUid, data: { info: { name: 'Updated by another client' } } } }
    )
    expect((await changedOutsidePage.json()).code).toBe(200)
    await expect(
      page.getByRole('tab', { name: 'Updated by another client', exact: true })
    ).toBeVisible({
      timeout: 4000,
    })
    await app.evidence('games-tab-light')
    await page.setViewportSize({ width: 1100, height: 650 })
    await page.getByRole('button', { name: /Add game target/ }).click()
    await expect(dialog.getByRole('combobox')).toBeInViewport()
    await expect(dialog.getByRole('button', { name: 'OK', exact: true })).toBeInViewport()
    await app.evidence('games-add-low-height')
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
    await app.goto('/settings')
    await page.locator('.theme-mode-control .ant-segmented-item').nth(2).click()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await app.goto('/games')
    await app.evidence('games-tab-dark')

    const base = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`
    const post = async (route: string, data: object) => {
      const response = await page.request.post(base + route, { data })
      expect(response.ok()).toBe(true)
      const body = await response.json()
      expect(body.code, body.message).toBe(200)
      return body
    }
    const games = await post('/api/games/get', {})
    const defaultId = games.order[0].uid
    const second = await post('/api/games/create', {
      type: 'general_emulator',
      data: { info: { name: 'Account override target' } },
    })
    const overrideId = second.order[0].uid
    const script = await post('/api/scripts/add', { type: 'SRC' })
    const account = await post('/api/scripts/user/add', { scriptId: script.scriptId })
    await post('/api/scripts/update', {
      scriptId: script.scriptId,
      data: { game: { game_id: defaultId, device_id: '-' } },
    })
    await post('/api/scripts/user/update', {
      scriptId: script.scriptId,
      userId: account.userId,
      data: { game: { game_id: overrideId, device_id: '-' } },
    })
    await app.goto(`/scripts/${script.scriptId}/users/${account.userId}/edit/src`)
    await expect(page.locator('.game-binding-card')).toContainText('Account override target')
    await app.evidence('games-account-override-dark')
    await post('/api/games/delete', { gameId: defaultId })
    const savedScript = await post('/api/scripts/get', { scriptId: script.scriptId })
    const savedAccount = await post('/api/scripts/user/get', {
      scriptId: script.scriptId,
      userId: account.userId,
    })
    expect(savedScript.data[script.scriptId].game.game_id).toBe('-')
    expect(savedAccount.data[account.userId].game.game_id).toBe(overrideId)

    const executable = test.info().outputPath('offline-game-fixture.exe')
    await writeFile(executable, '')
    const windows = await post('/api/games/create', {
      type: 'win_process',
      data: { info: { name: 'Offline Windows target', path: executable } },
    })
    const client = windows.data[windows.order[0].uid]
    expect(client.devices.order).toHaveLength(1)
    const device = client.devices.data[client.devices.order[0].uid]
    expect(device.info.status).toBe(1)
    await app.goto('/games')
    await page.getByRole('tab', { name: 'Offline Windows target', exact: true }).click()
    await expect(panel.getByRole('row').filter({ hasText: 'Offline Windows target' })).toBeVisible()
    await expect(panel.getByRole('button', { name: /add connection/i })).toHaveCount(0)
    await app.evidence('games-windows-tab-dark')
    await post('/api/scripts/delete', { scriptId: script.scriptId })
    await post('/api/games/delete', { gameId: overrideId })
    await post('/api/games/delete', { gameId: windows.order[0].uid })
  })
})
