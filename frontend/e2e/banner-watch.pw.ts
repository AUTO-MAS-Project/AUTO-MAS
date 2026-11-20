import { expect, test } from './fixtures'

test('calendar banner settings and reviewed analysis fallback @banner-watch', async ({
  app,
  page,
}) => {
  const banner = {
    id: 'fixture-pool',
    game: 'endfield',
    server: 'cn',
    title: 'QA banner',
    kind: 'weapon',
    start_mode: 'scheduled',
    starts_at: '2026-11-19T17:00:00Z',
    ends_at: '2026-12-04T04:00:00Z',
    confirmed_open_at: null,
    official_url: 'https://endfield.hypergryph.com/news/7204',
    verified_at: '2026-11-19T22:00:00Z',
    status: 'open',
    stale: true,
  }
  const state = {
    games: [
      {
        id: 'endfield',
        name: 'Endfield',
        servers: [
          { id: 'cn', name: 'CN', covered: true, managed: true },
          { id: 'global', name: 'Global', covered: false, managed: true },
        ],
      },
    ],
    subscriptions: [] as { game: string; server: string }[],
    subscriptionRevision: 0,
    banners: [banner],
    sources: [],
    hasNotificationChannels: false,
  }
  await page.route('**/api/banner-watch', route => route.fulfill({ json: state }))
  await page.route('**/api/banner-watch/subscriptions', async route => {
    expect(route.request().postDataJSON()).toEqual({
      subscriptionRevision: 0,
      subscriptions: [{ game: 'endfield', server: 'cn' }],
    })
    state.subscriptions = [{ game: 'endfield', server: 'cn' }]
    state.subscriptionRevision = 1
    await route.fulfill({ json: state })
  })
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await app.goto('/taskboard')
  const tab = page.getByRole('tab', { name: /Banners|卡池/ })
  await tab.click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText(/No global notification channels|尚未启用全局通知渠道/)).toBeVisible()
  await page.getByRole('button', { name: /Manage follows|关注设置/i }).click()
  await expect(page.getByRole('checkbox', { name: /^CN/ })).toBeChecked()
  await expect(page.getByRole('checkbox', { name: /^Global/ })).toBeDisabled()
  await page.getByRole('button', { name: /Save|保存关注/i }).click()
  await expect(page.getByRole('heading', { name: 'QA banner' })).toBeVisible()
  await expect(
    page
      .locator('.watch')
      .getByText(/Announced start time reached|按公告已到开池时间/)
      .first()
  ).toBeVisible()
  await expect(page.locator('.watch').getByText(/01:00/).first()).toBeVisible()
  await expect(
    page.getByRole('link', { name: /Read official notice|查看官方公告/ })
  ).toHaveAttribute('href', banner.official_url)
  await page.getByRole('button', { name: /Ask Agent|让 Agent 分析/i }).click()
  await page.getByRole('textbox', { name: /Pull inventory|库存/ }).fill('30 pulls')
  await page.getByRole('button', { name: /Preview|生成分析请求预览/i }).click()
  const preview = page.getByRole('textbox', { name: /Editable|可编辑/ })
  await expect(preview).toHaveValue(/30 pulls/)
  await expect(preview).toHaveValue(/endfield\.hypergryph\.com\/news\/7204/)
  const reviewed = (await preview.inputValue()) + '\n[Review marker]'
  await preview.fill(reviewed)
  await page.getByRole('button', { name: /Confirm.*Codex|确认交给本地 Codex/i }).click()
  await expect(page.locator('.watch').getByRole('status')).toContainText(/copied|已复制/i)
  const copied = await page.evaluate(() => navigator.clipboard.readText())
  expect(copied.replace(/\r\n/g, '\n')).toBe(reviewed)
  await app.evidence('banner-watch')
  await page.getByRole('tab', { name: /Active|进行中/i }).click()
  await expect(page.getByRole('heading', { name: 'QA banner' })).toHaveCount(0)
})
