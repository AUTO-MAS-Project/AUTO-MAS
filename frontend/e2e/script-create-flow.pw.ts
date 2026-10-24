import { expect, test } from './fixtures'

/**
 * @config 新建脚本向导：真实用户最常走的一条路。
 *
 * 为什么单独一条：script-editors.pw.ts 是直接调接口造数据再打开编辑页，
 * 而用户是从「New managed script」进向导（选类型 → 必要时选配置来源 → 创建 → 落到编辑页）。
 * 这条路上任何一环坏掉（类型列表少了、搜索过滤失效、主按钮文案/启用状态不对、创建后没跳转），
 * 接口层用例都发现不了。
 *
 * 向导步骤数由 scriptCreateFlow.ts:216 的 buildCreateSteps 决定：General 两步（类型 → 配置来源），
 * MaaFW 家族两步（类型 → 项目来源），其余类型一步直接建。两种形态各一条用例，避免只覆盖一边。
 */
type Page = import('@playwright/test').Page

const openWizard = async (app: { goto: (route: string) => Promise<void> }, page: Page) => {
  await app.goto('/scripts')
  await page.getByRole('button', { name: 'New managed script' }).click()
  const dialog = page.locator('.script-create-dialog')
  await expect(dialog).toBeVisible()
  return dialog
}

const pickType = async (page: Page, title: string) => {
  const dialog = page.locator('.script-create-dialog')
  const row = dialog.locator('.type-row').filter({
    has: page.locator('.choice-title', { hasText: new RegExp('^' + title + '$') }),
  })
  await expect(row, '类型列表里找不到 ' + title).toHaveCount(1)
  await row.click()
}

const scriptIdFromHash = (page: Page) => new URL(page.url()).hash.split('/')[2]

test.describe('@config script create wizard', () => {
  test('选型搜索可用，一步类型直接创建并落到编辑页', async ({ app, page }) => {
    let createdScriptId: string | undefined
    try {
      const dialog = await openWizard(app, page)

      // 类型列表把注册表里的类型都摆出来（少一个 = 用户建不了那种脚本）
      const typeRows = dialog.locator('.type-row')
      await expect(typeRows).toHaveCount(14)

      // 搜索按类型名过滤
      const search = dialog.locator('.list-toolbar input').first()
      await search.fill('zzz')
      await expect(typeRows).toHaveCount(1)
      await expect(typeRows.first()).toContainText('ZZZ-OD')

      // 搜不到时给「没有匹配的类型 + 清空搜索」，而不是一片空白
      await search.fill('no-such-script-type')
      await expect(dialog.locator('.ant-empty')).toBeVisible()
      await dialog.getByRole('button', { name: 'Clear search' }).click()
      await expect(typeRows).toHaveCount(14)

      // MAA 只有一步：主按钮直接就是「创建并配置」，点了就该进编辑页
      await pickType(page, 'MAA')
      const primary = dialog.getByRole('button', { name: 'Create and configure' })
      await expect(primary).toBeEnabled()
      await primary.click()

      await expect
        .poll(() => new URL(page.url()).hash, { timeout: 20_000 })
        .toMatch(/^#\/scripts\/[0-9a-f-]{36}\/edit\/maa$/)
      createdScriptId = scriptIdFromHash(page)
      await expect(page.locator('.config-card .ant-card-head-title').first()).toContainText(
        'MAA script configuration'
      )
      await app.evidence('script-created-one-step')
    } finally {
      if (createdScriptId) await app.api.post('/api/scripts/delete', { scriptId: createdScriptId })
    }
  })

  test('General 走两步：先选类型再选自定义配置，创建后落到编辑页', async ({ app, page }) => {
    let createdScriptId: string | undefined
    try {
      const dialog = await openWizard(app, page)
      await pickType(page, 'General')

      // 第一步（类型）的主按钮是「下一步」，不是直接创建
      await dialog.getByRole('button', { name: 'Next' }).click()
      await expect(dialog).toContainText('Pick a configuration source')

      // 第二步选自定义：模板来自配置中心，浏览器预览里未必连得上，自定义才是可预期的那条
      await dialog
        .locator('.choice-row')
        .filter({ has: page.locator('.choice-title', { hasText: 'Custom configuration' }) })
        .click()
      const primary = dialog.getByRole('button', { name: 'Create and configure' })
      await expect(primary).toBeEnabled()
      await primary.click()

      await expect
        .poll(() => new URL(page.url()).hash, { timeout: 20_000 })
        .toMatch(/^#\/scripts\/[0-9a-f-]{36}\/edit\/general$/)
      createdScriptId = scriptIdFromHash(page)
      await expect(page.locator('.config-card .ant-card-head-title').first()).toContainText(
        'General script configuration'
      )
      await app.evidence('script-created-two-step')
    } finally {
      if (createdScriptId) await app.api.post('/api/scripts/delete', { scriptId: createdScriptId })
    }
  })
})
