import type { Page, Response } from '@playwright/test'
import { expect, test } from './fixtures'

// 被驱动的用户路径：游戏社区工具（frontend/src/views/gamesign/index.vue）。
// 后端入口在 app/api/tools.py，签到编排在 app/tools/community_sign*.py。
// 这条流程锁住四件事：页面能渲染、设置能落盘、账号组 CRUD 能用、
// 手动签到与日常便笺查询仍走通——把社区代码收束到 app/tools/ 之后，
// 任何导入路径、路由挂载或载荷字段写坏都会在这里先炸。

const postOk = (page: Page, path: string, timeout = 30_000) =>
  page.waitForResponse(
    response =>
      response.url().endsWith(path) &&
      response.request().method() === 'POST' &&
      response.ok(),
    { timeout }
  )

const jsonOf = async (response: Response) => (await response.json()) as Record<string, unknown>

const settingSwitch = (page: Page, title: string) =>
  page.locator('.setting-row').filter({ hasText: title }).locator('.ant-switch')

const isChecked = (page: Page, title: string) =>
  settingSwitch(page, title).evaluate(el => el.classList.contains('ant-switch-checked'))

test.describe('@community game community tool', () => {
  test('settings, accounts, manual check-in and daily notes survive the tools consolidation', async ({
    app,
    page,
  }) => {
    const pageErrors: string[] = []
    page.on('pageerror', error => pageErrors.push(String(error)))

    // 1. 页面与页签（路由 /gamesign + 社区工具页根节点）
    await app.goto('/gamesign')
    await expect(page.locator('.gamesign-container')).toBeVisible()
    await expect(page.locator('.gamesign-container .page-title')).toHaveText('Game Community')
    await expect(page.getByRole('tab', { name: 'Check-ins' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Daily notes' })).toBeVisible()

    // 2. 设置区：开关写配置（POST /api/tools/update，配置契约不能被收束改坏）
    await expect(page.getByText('Community settings', { exact: true })).toBeVisible()
    for (const title of [
      'Enable community tools',
      'Enable daily notes',
      'Notify on completion',
      'Check in at startup',
    ]) {
      await expect(settingSwitch(page, title)).toBeVisible()
    }

    if (!(await isChecked(page, 'Enable community tools'))) {
      const saved = postOk(page, '/api/tools/update')
      await settingSwitch(page, 'Enable community tools').click()
      const body = await jsonOf(await saved)
      expect(body.code, '保存社区工具开关的业务码').toBe(200)
    }
    await expect(settingSwitch(page, 'Enable community tools')).toHaveClass(/ant-switch-checked/)

    // 3. 账号组：空态 → 新增 → 改名 → 删除（list/add/update/delete 四条契约）
    const listResponse = postOk(page, '/api/tools/sign/account/list')
    await page.reload()
    expect((await jsonOf(await listResponse)).code, '账号组列表的业务码').toBe(200)
    await expect(page.getByText('No accounts yet', { exact: true })).toBeVisible()

    const created = postOk(page, '/api/tools/sign/account/add')
    await page.getByRole('button', { name: 'Add an account' }).click()
    expect((await jsonOf(await created)).code, '新增账号组的业务码').toBe(200)
    await expect(page.locator('.user-row')).toHaveCount(1)

    const row = page.locator('.user-row').first()
    const defaultName = (await row.locator('.user-name-text').innerText()).trim()
    expect(defaultName, '新增账号组应有默认名称').not.toBe('')

    // 新增后页面会直接打开编辑弹窗（TabGameSign.vue:186），不必再点行内「编辑」
    const modal = page.locator('.ant-modal-content')
    await expect(modal).toBeVisible()
    await expect(modal.locator('.ant-modal-title')).toContainText(defaultName)
    await modal.locator('.form-item-vertical').first().locator('input').fill('E2E Community')
    const updated = postOk(page, '/api/tools/sign/account/update')
    await modal.getByRole('button', { name: 'Save' }).click()
    expect((await jsonOf(await updated)).code, '更新账号组的业务码').toBe(200)
    await expect(modal).toBeHidden()
    // 改名后必须刷新列表，不能停留在旧名字
    await expect(page.locator('.user-name-text')).toHaveText('E2E Community')

    await app.evidence('community-account-renamed')

    // 4. 手动签到：入口仍可用，结果写回配置（无凭据时只要求流程跑完且页面不崩）
    const signed = postOk(page, '/api/tools/sign', 60_000)
    await page.getByRole('button', { name: 'Check in everywhere' }).click()
    expect((await jsonOf(await signed)).code, '手动签到的业务码').toBe(200)
    await expect(page.getByRole('button', { name: 'Check in everywhere' })).toBeEnabled()
    await expect(page.locator('.user-row')).toHaveCount(1)
    await expect(page.getByText('Last check-in', { exact: true })).toBeVisible()

    // 5. 日常便笺页签：查询接口仍挂载，空态不能显示成错误
    const queried = postOk(page, '/api/tools/community/activity/query')
    await page.getByRole('tab', { name: 'Daily notes' }).click()
    await expect(page.locator('.activity-view')).toBeVisible()
    expect((await jsonOf(await queried)).code, '日常便笺查询的业务码').toBe(200)
    await expect(page.locator('.activity-view .activity-title')).toHaveText('Daily notes')
    await expect(
      page.locator('.activity-view .activity-state, .activity-view .activity-grid').first()
    ).toBeVisible()

    await app.evidence('community-daily-notes')

    // 6. 删除账号组并关掉开关，把隔离数据根恢复到初始状态
    await page.getByRole('tab', { name: 'Check-ins' }).click()
    const deleted = postOk(page, '/api/tools/sign/account/delete')
    await page.locator('.user-row').first().getByRole('button', { name: 'Delete' }).click()
    const confirm = page.locator('.ant-modal-confirm')
    await expect(confirm).toBeVisible()
    await confirm.getByRole('button', { name: 'Delete' }).click()
    expect((await jsonOf(await deleted)).code, '删除账号组的业务码').toBe(200)
    await expect(page.getByText('No accounts yet', { exact: true })).toBeVisible()

    const disabled = postOk(page, '/api/tools/update')
    await settingSwitch(page, 'Enable community tools').click()
    expect((await jsonOf(await disabled)).code, '关闭社区工具的业务码').toBe(200)
    await expect(settingSwitch(page, 'Enable community tools')).not.toHaveClass(
      /ant-switch-checked/
    )

    // 收束后社区页不允许出现未捕获异常（缺模块、循环导入都会在这里冒出来）
    expect(pageErrors, `社区页出现未捕获异常: ${pageErrors.join(' | ')}`).toEqual([])
  })
})
