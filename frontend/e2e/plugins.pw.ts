import { expect, test } from './fixtures'

test.describe('@plugins plugin foundation', () => {
  test('blocks creation on capability failure and reloads available types on retry', async ({
    app,
    page,
  }) => {
    // 类型查询失败不回退到静态卡片；用户重试成功后才能继续创建。
    await page.route('**/api/scripts/types', route =>
      route.fulfill({ status: 503, json: { detail: 'unavailable' } })
    )
    await app.goto('/scripts')
    await page.getByRole('button', { name: /New managed script$/ }).click()
    const dialog = page.getByRole('dialog', { name: /New managed script$/ })
    await expect(dialog.locator('.ant-alert-error')).toBeVisible()
    await expect(dialog.getByRole('radio')).toHaveCount(0)
    await expect(dialog.locator('.ant-empty')).toHaveCount(0)
    await expect(dialog.locator('.dialog-footer .ant-btn-primary')).toBeDisabled()
    await page.unroute('**/api/scripts/types')
    await dialog.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(dialog.getByRole('radio', { name: /^MAA / })).toBeVisible()
    await expect(dialog.locator('.dialog-footer .ant-btn-primary')).toBeEnabled()
  })
  test('uses NoData for empty plugin pages without hiding failures', async ({ app, page }) => {
    // 从公开接口返回合法空数据，检查三页统一空态，失败时不伪装成没有配置。
    await page.route('**/api/plugin_registry/get?*', route =>
      route.fulfill({
        json: { code: 200, order: [], data: {} },
      })
    )
    await page.route('**/api/plugin_catalog/get?*', route =>
      route.fulfill({
        json: { code: 200, order: [], data: {} },
      })
    )
    await page.route('**/api/plugin_config/get?*', route =>
      route.fulfill({
        json: { code: 200, data: null },
      })
    )
    for (const path of ['/plugins', '/plugins/market', '/plugins/empty/settings']) {
      await app.goto(path)
      await expect(page.locator('main .ant-empty img')).toHaveAttribute(
        'src',
        /^(data:image\/svg\+xml,|.*NoData.*\.svg)/
      )
      await expect(page.locator('main .ant-alert-error')).toHaveCount(0)
    }
    await page.route('**/api/plugin_config/get?*', route =>
      route.fulfill({ status: 503, json: { detail: 'unavailable' } })
    )
    await app.goto('/plugins/failure/settings')
    await expect(page.locator('main .ant-alert-error')).toBeVisible()
    await expect(page.locator('main .ant-empty')).toHaveCount(0)
  })

  test('confirms adapter data deletion and updates an open creation dialog after real toggles', async ({
    app,
    page,
  }) => {
    // 使用同一个主连接，真实启停隔离 MAA 插件，检查确认与能力实时变化。
    const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
    const registry = await (
      await page.request.post(`${backend}/api/plugin_registry/get`, { data: {} })
    ).json()
    const record = (
      Object.values(registry.data) as Array<{ uid: string; info: { plugin_name: string } }>
    ).find(item => item.info.plugin_name === 'maa_adapter')!
    const command = async (field: 'enable' | 'disable') => {
      // 经公开命令接口模拟窗口打开期间的外部能力变化，等待真正完成。
      const accepted = await (
        await page.request.post(`${backend}/api/operations/start`, {
          data: { configUid: record.uid, group: 'info', field, value: true },
        })
      ).json()
      expect(accepted.code).toBe(200)
      await expect
        .poll(
          async () =>
            (
              await (
                await page.request.post(`${backend}/api/operations/get`, {
                  data: { operationId: accepted.data.operationId },
                })
              ).json()
            ).data.state
        )
        .toBe('succeeded')
    }
    const created = await (
      await page.request.post(`${backend}/api/scripts/add`, { data: { type: 'MAA' } })
    ).json()
    expect(created.code).toBe(200)
    const stageOptions = await page.request.post(
      `${backend}/api/plugin/maa_adapter/stages/options`,
      { data: { type: 'User' } }
    )
    expect(stageOptions.status()).toBe(200)
    expect((await stageOptions.json()).data).toEqual(
      expect.arrayContaining([expect.objectContaining({ value: '1-7' })])
    )
    try {
      await app.goto('/plugins')
      const toggle = page.getByRole('switch', { name: /maa_adapter/i })
      await expect(toggle).toBeChecked()
      await toggle.click()
      const confirm = page.getByRole('dialog').filter({ hasText: 'Disable plugin?' })
      await expect(confirm).toContainText('permanently delete')
      await expect(confirm).toContainText('managed scripts')
      await confirm.getByRole('button', { name: 'Cancel', exact: true }).click()
      await expect(toggle).toBeChecked()
      const preserved = await (
        await page.request.post(`${backend}/api/scripts/get`, {
          data: { scriptId: created.scriptId },
        })
      ).json()
      expect(preserved.code).toBe(200)
      await toggle.click()
      await page
        .getByRole('dialog')
        .filter({ hasText: 'Disable plugin?' })
        .getByRole('button', { name: 'Disable', exact: true })
        .click()
      await expect(toggle).not.toBeChecked()
      expect(
        (
          await page.request.post(`${backend}/api/plugin/maa_adapter/stages/options`, { data: {} })
        ).status()
      ).toBe(404)
      const removed = await (
        await page.request.post(`${backend}/api/scripts/get`, { data: {} })
      ).json()
      expect(removed.data[created.scriptId]).toBeUndefined()
      await app.goto('/scripts')
      await page.getByRole('button', { name: /New managed script$/ }).click()
      const dialog = page.getByRole('dialog', { name: /New managed script$/ })
      await expect(dialog.getByRole('radio', { name: /^General / })).toBeVisible()
      await expect(dialog.getByRole('radio', { name: /^MAA / })).toHaveCount(0)
      await command('enable')
      await expect(dialog.getByRole('radio', { name: /^MAA / })).toBeVisible()
      await dialog.getByRole('radio', { name: /^MAA / }).check()
      await command('disable')
      await expect(dialog.getByRole('radio', { name: /^MAA / })).toHaveCount(0)
      await expect(dialog.getByRole('radio', { name: /^General / })).toBeChecked()
      await command('enable')
      await expect(dialog.getByRole('radio', { name: /^MAA / })).toBeVisible()
      await app.evidence('plugins-live-script-capabilities')
    } finally {
      // 还原插件启用状态，避免当前场景影响后续公共流程。
      const current = await (
        await page.request.post(`${backend}/api/plugin_registry/get`, {
          data: { recordId: record.uid },
        })
      ).json()
      if (!current.data[record.uid].info.enabled) await command('enable')
      const scripts = await (
        await page.request.post(`${backend}/api/scripts/get`, { data: {} })
      ).json()
      if (scripts.data[created.scriptId]) {
        await page.request.post(`${backend}/api/scripts/delete`, {
          data: { scriptId: created.scriptId },
        })
      }
    }
  })
  // 组织插件基础能力的浏览器验证，覆盖插件中心、市场、主题和失败重试。
  test('shows bundled core and market in both themes', async ({ app, page }) => {
    // 通过真实页面检查 core 插件与市场入口，并在浅色和深色主题下保留展示证据。
    await app.goto('/plugins')
    const navigation = page.locator('.bottom-menu [role="menuitem"]')
    await expect(navigation.nth(3)).toContainText('Resource store')
    await expect(navigation.nth(4)).toContainText('Plugin center')
    await expect(page.getByRole('heading', { name: /Plugin center/ })).toBeVisible()
    await expect(page.getByRole('cell', { name: /AUTO-MAS Core/ }).first()).toBeVisible()
    await expect(page.locator('.plugins-page .ant-spin-blur')).toHaveCount(0)
    await expect(page.locator('.plugins-page .ant-spin-container')).toHaveCSS('opacity', '1')
    const coreSwitch = page.getByRole('switch', { name: /AUTO-MAS Core/ })
    await expect(coreSwitch).toBeChecked()
    await expect(coreSwitch).toBeDisabled()
    await expect(page.locator('.plugins-page h1')).toHaveClass('app-page-title')
    await app.evidence('plugins-core-light')
    await app.goto('/settings')
    await page.locator('.theme-mode-control').getByText('Dark', { exact: true }).click()
    await app.goto('/plugins')
    await expect(page.getByRole('cell', { name: /AUTO-MAS Core/ }).first()).toBeVisible()
    await expect(page.locator('.plugins-page .ant-spin-blur')).toHaveCount(0)
    await expect(page.locator('.plugins-page .ant-spin-container')).toHaveCSS('opacity', '1')
    await app.evidence('plugins-core-dark')
    await app.goto('/plugins/market')
    await expect(page.getByRole('heading', { name: /Plugin market/ })).toBeVisible()
  })
  test('shows load failure and retries through the public registry API', async ({ app, page }) => {
    // 让公开注册接口暂时失败，验证错误提示和重试按钮可恢复插件列表。
    const route = '**/api/plugin_registry/get?*'
    await page.route(route, request =>
      /* 仅为当前浏览器场景模拟注册接口暂时不可用，不修改真实后端状态。 */ request.fulfill({
        status: 503,
        json: { detail: 'unavailable' },
      })
    )
    await app.goto('/plugins')
    await expect(page.locator('.plugins-page .ant-alert-error')).toBeVisible()
    await page.unroute(route)
    await page
      .locator('.plugins-page .ant-alert-error')
      .getByRole('button', { name: /Retry/ })
      .click()
    await expect(page.getByRole('cell', { name: /AUTO-MAS Core/ }).first()).toBeVisible()
    await expect(page.locator('.plugins-page .ant-alert-error')).toHaveCount(0)
  })

  test('uses field UI metadata for plugin actions instead of deriving it from state', async ({
    app,
    page,
  }) => {
    // 保持 enabled 状态但改变字段属性，证明菜单遵循 UI 提示而不是前端状态判断。
    await page.route('**/api/plugin_registry/get?*', async route => {
      const response = await route.fetch()
      const body = await response.json()
      for (const record of Object.values(body.data) as Array<{
        ui: { hints: Record<string, unknown[]> }
      }>) {
        record.ui.hints.info = [
          { field: 'enable', component: 'button', editable: true },
          { field: 'disable', component: 'button', editable: false },
          { field: 'uninstall', component: 'button', editable: false },
        ]
      }
      await route.fulfill({ response, json: body })
    })
    await app.goto('/plugins')
    const coreSwitch = page.getByRole('switch', { name: /AUTO-MAS Core/ })
    await expect(coreSwitch).not.toBeChecked()
    await expect(coreSwitch).toBeEnabled()
    await page.getByRole('button', { name: 'More actions' }).first().click()
    await expect(page.getByRole('menuitem', { name: 'Reload', exact: true })).toHaveCount(0)
    await app.evidence('plugins-field-ui-actions')
  })

  test('submits an install command independently and then refreshes install availability', async ({
    app,
    page,
  }) => {
    // 仅替换公开接口边界，验证命令身份、轮询和安装完成后的 UI 禁用，不安装真实插件。
    const configUid = '47b17e9c-e285-4ef7-9002-676643210111'
    const operationId = '47b17e9c-e285-4ef7-9002-676643210222'
    let installed = false
    await page.route('**/api/plugin_catalog/get?*', route =>
      route.fulfill({
        json: {
          code: 200,
          order: [{ uid: configUid, type: 'PluginMeta' }],
          data: {
            [configUid]: {
              uid: configUid,
              info: { display_name: 'UI fixture' },
              ui: {
                hints: { info: [{ field: 'install', component: 'button', editable: !installed }] },
                tables: [],
              },
            },
          },
        },
      })
    )
    await page.route('**/api/operations/start', async route => {
      expect(route.request().postDataJSON()).toEqual({
        configUid,
        group: 'info',
        field: 'install',
        value: true,
      })
      await route.fulfill({
        json: { code: 200, data: { operationId, configUid, state: 'queued' } },
      })
    })
    await page.route('**/api/operations/get', async route => {
      expect(route.request().postDataJSON()).toEqual({ operationId })
      installed = true
      await route.fulfill({
        json: { code: 200, data: { operationId, configUid, state: 'succeeded' } },
      })
    })
    await app.goto('/plugins/market')
    const install = page.getByRole('button', { name: /Install$/ })
    await expect(install).toBeEnabled()
    await install.click()
    await expect(install).toBeDisabled()
    await app.evidence('plugins-install-field-disabled')
  })

  test('uses the settings config identity for commands and rereads its field availability', async ({
    app,
    page,
  }) => {
    // 注册项与自有配置使用不同 UID，按钮必须提交配置 UID，并遵循刷新后的 editable。
    const recordId = '47b17e9c-e285-4ef7-9002-676643210333'
    const configUid = '47b17e9c-e285-4ef7-9002-676643210444'
    let completed = false
    await page.route('**/api/plugin_registry/get?*', route =>
      route.fulfill({
        json: {
          code: 200,
          data: {
            [recordId]: {
              uid: recordId,
              info: { plugin_name: 'fixture' },
              ui: { hints: {}, tables: [] },
            },
          },
        },
      })
    )
    await page.route('**/api/plugin_config/get?*', route =>
      route.fulfill({
        json: {
          code: 200,
          data: {
            uid: configUid,
            setup: { run: false },
            ui: {
              hints: { setup: [{ field: 'run', component: 'button', editable: !completed }] },
              tables: [],
            },
          },
        },
      })
    )
    await page.route('**/api/operations/start', async route => {
      expect(route.request().postDataJSON()).toEqual({
        configUid,
        group: 'setup',
        field: 'run',
        value: true,
      })
      completed = true
      await route.fulfill({
        json: {
          code: 200,
          data: {
            operationId: '47b17e9c-e285-4ef7-9002-676643210555',
            configUid,
            state: 'succeeded',
          },
        },
      })
    })
    await app.goto(`/plugins/${recordId}/settings`)
    const run = page.getByRole('button', { name: 'run', exact: true })
    await expect(run).toBeEnabled()
    await run.click()
    await expect(run).toBeDisabled()
    await app.evidence('plugins-settings-field-disabled')
  })
})
