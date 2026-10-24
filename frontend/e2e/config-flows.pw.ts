import { expect, test } from './fixtures'

// @config 配置类业务流：以真实用户路径走完一个管理脚本的全生命周期
// 「空列表 → 创建向导 → 编辑页改名 → 列表持久化 → 删除回到空列表」。
// 创建向导：frontend/src/views/Scripts.vue:59 按钮 → ScriptCreateDialog.vue（MAA 一步直接建，
// 见 scriptCreateFlow.ts:216 buildCreateSteps——只有 General 与 MFW 家族才有第二步）。
// 改名失焦即保存：frontend/src/views/EditView/Script/MAAScriptEdit.vue:65 @blur handleChange。
// 接口：POST /api/scripts/add、POST /api/scripts/update、POST /api/scripts/delete。

const scriptName = 'E2E lifecycle script'

const waitOk = (page: import('@playwright/test').Page, url: string) =>
  page.waitForResponse(
    response =>
      response.url().endsWith(url) && response.request().method() === 'POST' && response.ok(),
    { timeout: 15000 }
  )

test.describe('@config script lifecycle', () => {
  test('creates, renames, persists, and deletes a managed script', async ({ app, page }) => {
    // 非 real 运行的数据根是空的：先看到空状态
    await app.goto('/scripts')
    await expect(page.getByText('No managed scripts yet', { exact: true })).toBeVisible()

    // 打开创建向导；MAA 是默认选中项，一步就能建（没有第二步）
    await page.getByRole('button', { name: 'New managed script' }).click()
    const dialog = page.locator('.script-create-dialog')
    await expect(dialog).toBeVisible()

    const created = waitOk(page, '/api/scripts/add')
    await dialog.getByRole('button', { name: 'Create and configure' }).click()
    await created

    // 建完直接落到该类型的编辑页
    await expect
      .poll(() => new URL(page.url()).hash, { timeout: 20000 })
      .toMatch(/^#\/scripts\/[^/]+\/edit\/maa$/)
    await expect(page.getByText('MAA script configuration', { exact: true }).first()).toBeVisible()
    await app.evidence('config-script-edit-page')

    // 改名：失焦触发保存（等 /api/scripts/update 200 再往下走）
    const nameInput = page
      .locator('.ant-form-item')
      .filter({ hasText: 'Managed script name' })
      .locator('input')
    await nameInput.fill(scriptName)
    const renamed = waitOk(page, '/api/scripts/update')
    await nameInput.press('Tab')
    await renamed

    // 回列表：面包屑导航是用户真实路径
    await page.locator('.breadcrumb-link').click()
    await expect.poll(() => new URL(page.url()).hash).toBe('#/scripts')
    const nameCell = page.locator('.script-name', { hasText: scriptName })
    await expect(nameCell).toBeVisible()

    // 刷新后仍在：后端真的落了盘
    await page.reload()
    await expect(page.locator('.script-name', { hasText: scriptName })).toBeVisible()
    await app.evidence('config-script-persisted')

    // 删除：More 菜单 → Delete the managed script → 确认框 OK
    await page.getByRole('button', { name: 'More' }).click()
    await page.getByRole('menuitem', { name: 'Delete the managed script' }).click()
    const removed = waitOk(page, '/api/scripts/delete')
    await page.locator('.ant-modal-confirm').getByRole('button', { name: 'OK' }).click()
    await removed
    await expect(page.getByText('No managed scripts yet', { exact: true })).toBeVisible()
    await app.evidence('config-script-deleted')
  })
})
