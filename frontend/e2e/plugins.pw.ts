import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.describe('@plugins plugin foundation', () => {
  const refreshEndpoint = '**/api/plugin_catalog/refresh?*'
  // 插件中心的三个页签、市场卡片与已安装行；文字定位，不依赖表格结构。
  const centerTab = (page: Page, name: 'Installed' | 'Market' | 'Updates') =>
    page.locator('.plugin-center .ant-segmented-item').filter({ hasText: new RegExp(`^${name}`) })
  const marketCard = (page: Page, name: string) =>
    page.locator('.market-card').filter({ hasText: name })
  const installedRow = (page: Page, name: string | RegExp) =>
    page.locator('.installed-row').filter({ hasText: name })

  test.beforeEach(async ({ page }) => {
    await page.route(refreshEndpoint, route => route.fulfill({ json: { code: 200 } }))
  })

  test('shows local market entries while the catalog refreshes on entry', async ({ app, page }) => {
    const uid = '47b17e9c-e285-4ef7-9002-676643210882'
    let version = '1.0'
    let refreshes = 0
    let releaseRefresh: (() => void) | undefined
    const refreshGate = new Promise<void>(resolve => {
      releaseRefresh = resolve
    })
    await page.route('**/api/plugin_catalog/get?*', route =>
      route.fulfill({
        json: {
          code: 200,
          order: [{ uid, type: 'PluginMeta' }],
          data: { [uid]: { uid, info: { display_name: 'Test adapter', version } } },
        },
      })
    )
    await page.route(refreshEndpoint, async route => {
      refreshes += 1
      if (refreshes > 1) {
        await route.fulfill({ json: { code: 500, message: 'Offline' } })
        return
      }
      await refreshGate
      version = '2.0'
      await route.fulfill({ json: { code: 200 } })
    })

    const cardVersion = () => marketCard(page, 'Test adapter').locator('.market-card-sub')
    try {
      const refreshing = page.waitForRequest(refreshEndpoint)
      await app.goto('/plugins/market')
      await refreshing
      await expect(cardVersion()).toHaveText('1.0')
      await page.getByRole('button', { name: /Refresh catalog$/ }).click()
    } finally {
      releaseRefresh?.()
    }
    await expect(cardVersion()).toHaveText('2.0')
    await expect(page.getByText('Plugin market refreshed', { exact: true })).toBeVisible()
    expect(refreshes).toBe(1)

    await app.goto('/plugins')
    await expect(page.getByRole('heading', { name: 'Plugin center' })).toBeVisible()
    const refreshFailed = page.waitForResponse(refreshEndpoint)
    await app.goto('/plugins/market')
    await refreshFailed
    await expect(cardVersion()).toHaveText('2.0')
    await expect(page.getByText('Offline', { exact: true })).toHaveCount(0)
  })

  test('updates the installed page when a market refresh outlives navigation and leaving the center', async ({
    app,
    page,
  }) => {
    let uid = '47b17e9c-e285-4ef7-9002-676643210882'
    let version = '0.1.4'
    let releaseRefresh: (() => void) | undefined
    const refreshGate = new Promise<void>(resolve => {
      releaseRefresh = resolve
    })
    await page.route('**/api/plugin_catalog/get?*', route =>
      route.fulfill({
        json: {
          code: 200,
          order: [{ uid, type: 'PluginMeta' }],
          data: {
            [uid]: {
              uid,
              info: { plugin_name: 'maa_adapter', version, update_available: true },
              ui: {
                hints: { info: [{ field: 'install', component: 'button', editable: true }] },
                tables: [],
              },
            },
          },
        },
      })
    )
    await page.route(refreshEndpoint, async route => {
      await refreshGate
      uid = '47b17e9c-e285-4ef7-9002-676643210883'
      version = '0.1.5'
      await route.fulfill({ json: { code: 200 } })
    })

    try {
      const refreshing = page.waitForRequest(refreshEndpoint)
      await app.goto('/plugins/market')
      await refreshing
      // 市场的「返回」已并入页签：切回「已安装」，刷新仍在进行。
      await centerTab(page, 'Installed').click()
      await expect(page).toHaveURL(/#\/plugins$/)
      await expect(page.getByRole('button', { name: 'Update to 0.1.4', exact: true })).toBeVisible()
      // 三个页签共用一个外壳实例，切页签不算离开：再真正离开插件中心，刷新仍在进行。
      await page.evaluate(() => {
        window.location.hash = '#/scripts'
      })
      await expect(page).toHaveURL(/#\/scripts$/)
      await expect(page.locator('.plugins-page')).toHaveCount(0)
      // 放行后刷新在页外完成，并回读目录。
      const readBack = page.waitForResponse('**/api/plugin_catalog/get?*')
      releaseRefresh?.()
      await readBack
      await page.evaluate(() => {
        window.location.hash = '#/plugins'
      })
      await expect(page).toHaveURL(/#\/plugins$/)
    } finally {
      releaseRefresh?.()
    }
    await expect(page.getByRole('button', { name: 'Update to 0.1.5', exact: true })).toBeVisible()
  })

  test('upgrades market plugins from both pages and preserves retry after rejection', async ({
    app,
    page,
  }) => {
    // 两页复用市场触发器，防止误用注册 UID，并检查后台失败后仍可重试。
    const recordId = '47b17e9c-e285-4ef7-9002-676643210881'
    const metaId = '47b17e9c-e285-4ef7-9002-676643210882'
    const operationId = '47b17e9c-e285-4ef7-9002-676643210883'
    let installed = '1.0'
    let reject = true
    const info = {
      plugin_name: 'upgrade_fixture',
      package_name: 'auto-mas-upgrade-fixture',
      display_name: 'Upgrade fixture',
    }
    for (const resource of ['plugin_registry', 'plugin_catalog']) {
      await page.route(`**/api/${resource}/get?*`, route => {
        const market = resource === 'plugin_catalog'
        const uid = market ? metaId : recordId
        return route.fulfill({
          json: {
            code: 200,
            order: [{ uid, type: market ? 'PluginMeta' : 'PluginRecord' }],
            data: {
              [uid]: {
                uid,
                info: market
                  ? {
                      ...info,
                      version: '2.0',
                      changelog: [
                        { version: '2.0', body: '- New release change' },
                        { version: '1.5', body: '- Intermediate release change' },
                        { version: '1.0', body: '- Installed release change' },
                      ],
                      changelog_versions: {
                        target: '2.0',
                        installed,
                        updates: installed === '2.0' ? [] : ['2.0', '1.5'],
                      },
                      installed_version: installed,
                      update_available: installed !== '2.0',
                    }
                  : {
                      ...info,
                      version: installed,
                      enabled: true,
                      state: 'enabled',
                      source: 'installed',
                    },
                disableImpact: [],
                ui: {
                  hints: {
                    info: [
                      {
                        field: 'install',
                        component: 'button',
                        editable: market && installed !== '2.0',
                      },
                    ],
                  },
                  tables: [],
                },
              },
            },
          },
        })
      })
    }
    await page.route('**/api/operations/start', route => {
      expect(route.request().postDataJSON()).toEqual({
        configUid: metaId,
        group: 'info',
        field: 'install',
        value: true,
      })
      return route.fulfill({
        json: { code: 200, data: { operationId, configUid: metaId, state: 'queued' } },
      })
    })
    await page.route('**/api/operations/get', route => {
      if (!reject) installed = '2.0'
      return route.fulfill({
        json: {
          code: 200,
          data: {
            operationId,
            configUid: metaId,
            state: reject ? 'failed' : 'succeeded',
            errorCode: reject ? 'PluginPrecheckError' : null,
          },
        },
      })
    })
    await app.goto('/plugins/updates')
    const updateRow = page.locator('.update-row').filter({ hasText: 'Upgrade fixture' })
    await updateRow.getByRole('button', { name: 'Release notes' }).click()
    await expect(updateRow.getByText('New release change', { exact: true })).toBeVisible()
    await expect(updateRow.getByText('Intermediate release change', { exact: true })).toBeVisible()
    await expect(updateRow.getByText('Installed release change', { exact: true })).toHaveCount(0)
    await app.evidence('plugin-update-notes')
    for (const path of ['/plugins', '/plugins/market']) {
      installed = '1.0'
      reject = true
      await app.goto(path)
      const upgrade = page.getByRole('button', { name: 'Update to 2.0', exact: true })
      await expect(upgrade).toBeEnabled()
      await upgrade.click()
      await expect(page.locator('.ant-message')).toContainText('Action failed')
      await expect(upgrade).toBeEnabled()
      reject = false
      await upgrade.click()
      await expect(upgrade).toHaveCount(0)
      if (path === '/plugins/market')
        await expect(
          marketCard(page, 'Upgrade fixture').getByText('Installed', { exact: true })
        ).toBeVisible()
      else {
        const row = installedRow(page, 'Upgrade fixture')
        await expect(row).toContainText('2.0')
        await row.locator('.installed-row-main').click()
        await row.getByRole('button', { name: 'Release notes' }).click()
        await expect(row.getByText('New release change', { exact: true })).toBeVisible()
        await expect(row.getByText('Intermediate release change', { exact: true })).toHaveCount(0)
      }
    }
  })

  test('shows complete metadata and opens documentation from market and installed details', async ({
    app,
    page,
    context,
  }) => {
    // 仅隔离接口与外站访问，验证同一份发行元信息在两页均可展开查看、链接可打开。
    const uid = '47b17e9c-e285-4ef7-9002-676643210777'
    let invalid = false
    const info = {
      display_name: 'Metadata fixture',
      plugin_name: 'metadata_fixture',
      package_name: 'auto-mas-metadata-fixture',
      version: '1.2.3',
      description: 'Complete adapter metadata',
      author: 'Fixture Team',
      license: 'AGPL-3.0-or-later',
      tags: ['Adapter', 'Fixture'],
      requires_dist: ['auto-mas-core>=5.8,<5.9', 'httpx>=0.28'],
      docs_url: 'https://example.org/metadata-guide',
      homepage: 'https://example.org/metadata-home',
      repository: 'https://example.org/metadata-source',
      state: 'disabled',
    }
    for (const resource of ['plugin_catalog', 'plugin_registry']) {
      await page.route(`**/api/${resource}/get?*`, route =>
        route.fulfill({
          json: {
            code: 200,
            order: [{ uid, type: resource === 'plugin_catalog' ? 'PluginMeta' : 'PluginRecord' }],
            data: {
              [uid]: {
                uid,
                info: invalid
                  ? { ...info, author: null, license: null, docs_url: 'javascript:alert(1)' }
                  : info,
                ui: { hints: {}, tables: [] },
                disableImpact: [],
              },
            },
          },
        })
      )
    }
    await context.route('https://example.org/metadata-guide', route =>
      route.fulfill({ body: '<h1>Plugin documentation</h1>', contentType: 'text/html' })
    )
    const links = [
      ['Docs', info.docs_url],
      ['Homepage', info.homepage],
      ['Repository', info.repository],
    ] as const
    // 市场从卡片的「详情」打开弹层，已安装点行展开；名称与版本在标题区，其余字段在信息块。
    const openDetails = async (route: string) => {
      if (route === '/plugins/market') {
        const card = marketCard(page, info.display_name)
        await card.getByRole('button', { name: 'Details', exact: true }).click()
        return page.getByRole('dialog')
      }
      const row = installedRow(page, info.display_name)
      await row.locator('.installed-row-main').click()
      return row
    }
    for (const route of ['/plugins/market', '/plugins']) {
      await app.goto(route)
      if (route === '/plugins/market') {
        const card = marketCard(page, info.display_name)
        for (const tag of info.tags)
          await expect(card.getByText(tag, { exact: true })).toBeVisible()
        await expect(card.getByText('Source', { exact: true })).toHaveCount(0)
      }
      const container = await openDetails(route)
      const details = container.locator('.plugin-metadata')
      await expect(details).toBeVisible()
      for (const value of [info.display_name, info.version])
        await expect(container.getByText(value, { exact: true }).first()).toBeVisible()
      for (const value of [
        info.package_name,
        info.description,
        info.author,
        info.license,
        ...info.tags,
        ...info.requires_dist,
      ]) {
        await expect(details.getByText(value, { exact: true })).toBeVisible()
      }
      for (const [name, url] of links) {
        await expect(details.getByRole('link', { name, exact: true })).toHaveAttribute('href', url)
      }
      const popupPromise = page.waitForEvent('popup')
      await details.getByRole('link', { name: 'Docs', exact: true }).click()
      const popup = await popupPromise
      await expect(popup).toHaveURL(info.docs_url)
      await popup.close()
      for (const mode of ['light', 'dark'] as const) {
        await page.evaluate(async mode => {
          const modulePath = '/src/composables/useTheme.ts'
          const { useTheme } = await import(modulePath)
          await useTheme().setThemeMode(mode)
        }, mode)
        if (mode === 'dark') await expect(page.locator('html')).toHaveClass(/dark/)
        else await expect(page.locator('html')).not.toHaveClass(/dark/)
        await app.evidence(
          `${route === '/plugins' ? 'plugins' : 'market'}-complete-metadata-${mode}`
        )
      }
      if (route === '/plugins/market')
        await page
          .getByRole('dialog')
          .locator('.ant-modal-footer')
          .getByRole('button', { name: 'Close', exact: true })
          .click()
    }
    // 缺声明回落：非 http 链接当作没有，缺失的作者、许可证整格不显示，不放占位。
    invalid = true
    // 进入市场页签会重新读取目录，不必整页刷新。
    await app.goto('/plugins/market')
    const details = (await openDetails('/plugins/market')).locator('.plugin-metadata')
    await expect(details.getByText(info.description, { exact: true })).toBeVisible()
    await expect(details.getByText('javascript:alert(1)')).toHaveCount(0)
    await expect(details.getByRole('link', { name: 'Docs', exact: true })).toHaveCount(0)
    for (const [name, url] of links.slice(1))
      await expect(details.getByRole('link', { name, exact: true })).toHaveAttribute('href', url)
    for (const label of ['Author', 'License'])
      await expect(details.getByText(label, { exact: true })).toHaveCount(0)
    await expect(details.getByText('-', { exact: true })).toHaveCount(0)
  })

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
    for (const path of [
      '/plugins',
      '/plugins/market',
      '/plugins/updates',
      '/plugins/empty/settings',
    ]) {
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

  test('confirms uninstall before submitting a disabled adapter command', async ({ app, page }) => {
    // 隔离注册表与命令接口，验证已禁用适配器仍提示清空配置，取消不提交，确认仅提交一次。
    const configUid = '8f34836e-8498-4a6d-8fbe-a5d4db9d8ca6'
    const operationId = '9545fe42-3ef9-40d6-a0f0-b1b178bfb58b'
    let installed = true
    const submissions: unknown[] = []
    await page.route('**/api/plugin_registry/get?*', route =>
      route.fulfill({
        json: {
          code: 200,
          order: installed ? [{ uid: configUid, type: 'PluginRecord' }] : [],
          data: installed
            ? {
                [configUid]: {
                  uid: configUid,
                  info: {
                    display_name: 'Installed adapter',
                    state: 'disabled',
                    source: 'installed',
                  },
                  disableImpact: [],
                  ui: {
                    hints: { info: [{ field: 'uninstall', component: 'button', editable: true }] },
                    tables: [],
                  },
                },
              }
            : {},
        },
      })
    )
    await page.route('**/api/operations/start', route => {
      submissions.push(route.request().postDataJSON())
      return route.fulfill({
        json: { code: 200, data: { operationId, configUid, state: 'queued' } },
      })
    })
    await page.route('**/api/operations/get', route => {
      installed = false
      return route.fulfill({
        json: { code: 200, data: { operationId, configUid, state: 'succeeded' } },
      })
    })
    await app.goto('/plugins')
    const row = installedRow(page, 'Installed adapter')
    const uninstall = async () => {
      // 从插件中心的现有更多操作菜单打开卸载确认。
      await row.getByRole('button', { name: 'More actions', exact: true }).hover()
      await page.getByRole('menuitem', { name: 'Uninstall', exact: true }).click()
    }
    await uninstall()
    const confirm = page.getByRole('dialog').filter({ hasText: 'Uninstall plugin?' })
    await expect(confirm).toContainText('Installed adapter')
    await expect(confirm).toContainText('permanently delete')
    await expect(confirm).toContainText('managed scripts')
    await expect(confirm).toContainText('accounts')
    expect(submissions).toEqual([])
    await app.evidence('plugins-uninstall-confirm')
    await confirm.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(confirm).not.toBeVisible()
    await expect(row).toBeVisible()
    expect(submissions).toEqual([])
    await uninstall()
    await confirm.getByRole('button', { name: 'Uninstall', exact: true }).click()
    await expect(row).toHaveCount(0)
    expect(submissions).toEqual([{ configUid, group: 'info', field: 'uninstall', value: true }])
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
    const submissions: unknown[] = []
    page.on('request', request => {
      if (request.url().endsWith('/api/operations/start')) submissions.push(request.postDataJSON())
    })
    try {
      await app.goto('/plugins')
      // 带数据的专项不用行内开关，启停在「更多」里；状态看行内状态位。
      const row = installedRow(page, 'MAA Adapter')
      await expect(row.getByText('Running', { exact: true })).toBeVisible()
      await expect(row.getByRole('switch')).toHaveCount(0)
      const disable = async () => {
        await row.getByRole('button', { name: 'More actions', exact: true }).hover()
        await page.getByRole('menuitem', { name: 'Disable', exact: true }).click()
      }
      // 有托管在用时前端拦住：列出在用托管、引导去托管管理，不提交命令。
      await expect(row).toContainText('Managed scripts: 1')
      await disable()
      const guard = page.getByRole('dialog').filter({ hasText: "can't be disabled right now" })
      await expect(guard).toContainText('Managed scripts still using it: 1')
      await expect(guard.getByRole('button', { name: 'Go to managed scripts' })).toBeVisible()
      await app.evidence('plugins-disable-blocked-in-use')
      await guard
        .locator('.ant-modal-footer')
        .getByRole('button', { name: 'Close', exact: true })
        .click()
      await expect(guard).not.toBeVisible()
      expect(submissions).toEqual([])
      const preserved = await (
        await page.request.post(`${backend}/api/scripts/get`, {
          data: { scriptId: created.scriptId },
        })
      ).json()
      expect(preserved.code).toBe(200)
      // 删掉托管后照原流程：确认提示会永久删除专项数据，取消不提交，确认后停用。
      await page.request.post(`${backend}/api/scripts/delete`, {
        data: { scriptId: created.scriptId },
      })
      await page.reload()
      await expect(row.getByText('Running', { exact: true })).toBeVisible()
      await expect(row).not.toContainText('Managed scripts:')
      await disable()
      const confirm = page.getByRole('dialog').filter({ hasText: 'Disable plugin?' })
      await expect(confirm).toContainText('permanently delete')
      await expect(confirm).toContainText('managed scripts')
      await confirm.getByRole('button', { name: 'Cancel', exact: true }).click()
      await expect(confirm).not.toBeVisible()
      await expect(row.getByText('Running', { exact: true })).toBeVisible()
      expect(submissions).toEqual([])
      await disable()
      await page
        .getByRole('dialog')
        .filter({ hasText: 'Disable plugin?' })
        .getByRole('button', { name: 'Disable', exact: true })
        .click()
      await expect(row.getByText('Disabled', { exact: true })).toBeVisible()
      await expect(row.getByRole('button', { name: 'Enable', exact: true })).toBeVisible()
      expect(submissions).toEqual([
        { configUid: record.uid, group: 'info', field: 'disable', value: true },
      ])
      expect(
        (
          await page.request.post(`${backend}/api/plugin/maa_adapter/stages/options`, { data: {} })
        ).status()
      ).toBe(404)
      // 静态 MAA 页面仍随宿主交付，未提供能力时直达路由和计划创建入口均关闭。
      await page.goto(`/#/scripts/${created.scriptId}/users/missing/cultivate/maa`)
      await expect(page).toHaveURL(/#\/plugins\/market$/)
      await app.goto('/plans')
      await page.getByRole('button', { name: /^New plan/ }).click()
      await expect(page.getByRole('menuitem', { name: 'New MAA plan', exact: true })).toHaveCount(0)
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
      await app.goto('/plans')
      await page.getByRole('button', { name: /^New plan/ }).click()
      await expect(page.getByRole('menuitem', { name: 'New MAA plan', exact: true })).toBeVisible()
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
  test('re-reads managed usage on click so a script created after page load still blocks disable', async ({
    app,
    page,
  }) => {
    // 进页时没有托管；停留期间用公开接口新建一个，不刷新页面直接点停用，仍应被拦住且不提交命令。
    const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
    const submissions: unknown[] = []
    page.on('request', request => {
      if (request.url().endsWith('/api/operations/start')) submissions.push(request.postDataJSON())
    })
    let created: { scriptId?: string } = {}
    try {
      // 用量读取的最后一个请求是计划表；等它返回，保证进页快照确实不含下面新建的托管，
      // 否则点击时可能复用还在途的进页读取（守不住重取），或快照本身已含新托管（假绿）。
      const usageLoaded = page.waitForResponse(
        response =>
          response.url().endsWith('/api/plan/get') && response.request().method() === 'POST'
      )
      await app.goto('/plugins')
      const row = installedRow(page, 'MAA Adapter')
      await usageLoaded
      await expect(row.getByText('Running', { exact: true })).toBeVisible()
      await expect(row).not.toContainText('Managed scripts:')
      created = await (
        await page.request.post(`${backend}/api/scripts/add`, { data: { type: 'MAA' } })
      ).json()
      expect(created.scriptId).toBeTruthy()
      await row.getByRole('button', { name: 'More actions', exact: true }).hover()
      const item = page.getByRole('menuitem', { name: 'Disable', exact: true })
      await item.click()
      const guard = page.getByRole('dialog').filter({ hasText: "can't be disabled right now" })
      await expect(guard).toContainText('Managed scripts still using it: 1')
      expect(submissions).toEqual([])
      // 拦截弹层出现后「更多」菜单收起，不浮在弹层旁边。
      await expect(item).toBeHidden()
    } finally {
      if (created.scriptId)
        await page.request.post(`${backend}/api/scripts/delete`, {
          data: { scriptId: created.scriptId },
        })
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
    await expect(installedRow(page, 'AUTO-MAS Core').first()).toBeVisible()
    await expect(page.locator('.plugins-page .installed-skeleton')).toHaveCount(0)
    await expect(page.locator('.plugins-page .ant-spin-blur')).toHaveCount(0)
    // 核心插件不能停用：不放永远点不了的开关；版本是普通文字，来源标识为「Official」。
    const coreRow = installedRow(page, 'AUTO-MAS Core').first()
    await expect(page.getByRole('switch', { name: /AUTO-MAS Core/ })).toHaveCount(0)
    await expect(coreRow.locator('span.installed-row-version')).toBeVisible()
    await expect(coreRow.getByText('Official', { exact: true })).toBeVisible()
    await expect(coreRow.getByText('Local', { exact: true })).toHaveCount(0)
    await expect(page.locator('.installed-group-list .installed-row').first()).toBeVisible()
    await expect(page.locator('.installed-row-chevron')).toHaveCount(0)
    await expect(page.locator('.plugins-page h1')).toHaveClass('app-page-title')
    await app.evidence('plugins-core-light')
    await app.goto('/settings')
    await page.locator('.theme-mode-control').getByText('Dark', { exact: true }).click()
    await app.goto('/plugins')
    await expect(installedRow(page, 'AUTO-MAS Core').first()).toBeVisible()
    await expect(page.locator('.plugins-page .installed-skeleton')).toHaveCount(0)
    await expect(page.locator('.plugins-page .ant-spin-blur')).toHaveCount(0)
    await app.evidence('plugins-core-dark')
    await app.goto('/plugins/market')
    await expect(page.getByRole('heading', { name: /Plugin center/ })).toBeVisible()
    await expect(centerTab(page, 'Market')).toHaveClass(/ant-segmented-item-selected/)
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
    await expect(installedRow(page, 'AUTO-MAS Core').first()).toBeVisible()
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
