import { McpStatusData } from '../src/api/models/McpStatusData'
import { expect, test } from './fixtures'
import { observeMainConnection } from './socket-recovery'

test.describe('@tools MCP service', () => {
  test('shows real status after navigation, refresh and reconnect', async ({ app, page }) => {
    const socket = await observeMainConnection(page)
    await app.goto('/tools')
    const card = page.locator('.tools-page')
    await expect(card).toContainText('MCP service is ready', { timeout: 30_000 })
    const menu = page
      .getByRole('menuitem')
      .filter({ has: page.getByText('Tools', { exact: true }) })
    await expect(menu).toHaveClass(/ant-menu-item-selected/)
    await expect(card).toContainText('/mcp')
    await expect(card.locator('.ant-progress')).toHaveCount(0)
    await app.evidence('mcp-real-ready')
    await page.reload()
    await expect(card).toContainText('MCP service is ready')
    await socket.reconnect()
    await expect(card).toContainText('MCP service is ready')

    const startup = card.getByRole('switch', { name: 'Enable MCP at startup' })
    await expect(startup).toBeChecked()
    await page.route('**/api/setting/update', route =>
      route.fulfill({ json: { code: 500, status: 'error', message: 'Save failed for test' } })
    )
    await startup.click()
    await expect(page.getByText('Save failed for test', { exact: true })).toBeVisible()
    await expect(startup).toBeChecked()
    await page.unroute('**/api/setting/update')
    await startup.click()
    await expect(startup).not.toBeChecked()
    await expect(card).toContainText('Takes effect after restart')
    await expect(card).toContainText('MCP service is ready')
    await page.reload()
    await expect(startup).not.toBeChecked()
    await expect(card).toContainText('Takes effect after restart')
    await app.evidence('mcp-startup-disabled')
    await startup.click()
    await expect(startup).toBeChecked()
    await expect(card).not.toContainText('Takes effect after restart')
  })

  test('restores phases and retries a failure without treating acceptance as success', async ({
    app,
    page,
    request,
  }) => {
    const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
    await expect
      .poll(
        async () => (await (await request.get(`${backend}/api/core/mcp/status`)).json()).data.state
      )
      .toBe('ready')
    const socket = await observeMainConnection(page)
    let status: McpStatusData = {
      enabled: true,
      environmentEnabled: true,
      state: McpStatusData.state.PENDING,
      stage: null,
      startedAt: null,
      finishedAt: null,
      elapsedMs: 0,
      toolCount: 0,
      error: null,
      instanceId: 'browser-fixture',
      runId: 'attempt-1',
      revision: 0,
    }
    let snapshots = 0
    await page.route('**/api/core/mcp/status', async route => {
      snapshots++
      await route.fulfill({ json: { code: 200, data: status } })
    })
    await app.goto('/tools')
    const card = page.locator('.tools-page')
    await expect(card).toContainText('Waiting for application initialization')
    await expect.poll(() => socket.connections.length).toBeGreaterThan(0)
    const push = (next: Partial<McpStatusData>) => {
      status = { ...status, ...next, revision: status.revision + 1 }
      socket.connections
        .at(-1)!
        .route.send(JSON.stringify({ id: 'MCP', type: 'mcp.status.updated', data: status }))
    }
    for (const [stage, text] of [
      ['importing', 'Importing MCP dependencies'],
      ['building', 'Generating MCP tools'],
      ['validating', 'Validating MCP tools'],
      ['mounting', 'Preparing MCP service'],
    ] as const) {
      push({ state: McpStatusData.state.RUNNING, stage })
      await expect(card).toContainText(text)
      await expect(card.locator('.ant-progress')).toHaveCount(0)
    }
    await page.reload()
    await expect(card).toContainText('Preparing MCP service')
    const count = snapshots
    status = { ...status, stage: 'building', revision: status.revision + 1 }
    await socket.reconnect()
    await expect.poll(() => snapshots).toBeGreaterThan(count)
    await expect(card).toContainText('Generating MCP tools')
    push({ state: McpStatusData.state.FAILED, error: 'build_failed' })
    await expect(card).toContainText('Could not generate MCP tools')
    let release!: () => void
    const gate = new Promise<void>(resolve => {
      release = resolve
    })
    let retries = 0
    await page.route('**/api/core/mcp/retry', async route => {
      retries++
      status = {
        ...status,
        state: McpStatusData.state.RUNNING,
        stage: 'importing',
        runId: 'attempt-2',
        error: null,
        revision: status.revision + 1,
      }
      const accepted = status
      await gate
      await route.fulfill({ json: { code: 200, accepted: true, data: accepted } })
    })
    const reload = card.getByRole('button', { name: /Reload$/ })
    await reload.click()
    await expect(reload).toBeDisabled()
    expect(retries).toBe(1)
    release()
    await expect(card).toContainText('Importing MCP dependencies')
    await expect(card).not.toContainText('MCP service is ready')
    push({ state: McpStatusData.state.READY, toolCount: 81 })
    await expect(card).toContainText('MCP service is ready')
    await expect(card).toContainText('81')
    await expect(page.getByRole('button', { name: 'Reload', exact: true })).toHaveCount(0)
    await app.evidence('mcp-retry-ready')
    status = {
      ...status,
      enabled: false,
      state: McpStatusData.state.SKIPPED,
      revision: status.revision + 1,
    }
    await page.reload()
    await expect(card).toContainText('MCP service is disabled')
  })
})
