import { expect, test } from './fixtures'

/**
 * @plan 计划管理：MAS 里「脚本 → 计划 → 队列 → 调度」的主干中间环节，用户每天都要进出这一页。
 *
 * 这一页以前完全没有用例（只有 @routes 的「能打开」巡检），下面这些用户可感知的行为一条都没人守：
 *  - 没有计划时给的是空状态引导，而不是一张空表；
 *  - 新建计划的默认名跟随界面语言（历史实现把中文默认名写死，英文界面会凭空冒出中文计划名）；
 *  - 计划名改名后刷新还在（改的是持久化数据，不是内存里的显示值）；
 *  - 四种计划类型都能创建，且创建后真的渲染出各自的配置表；
 *  - 删掉最后一个计划回到空状态，不残留一个指向已删计划的配置区。
 */
type Page = import('@playwright/test').Page
type App = {
  goto: (route: string) => Promise<void>
  evidence: (name: string) => Promise<void>
  api: { post: (path: string, body?: unknown) => Promise<any> }
}

interface PlanIndexItem {
  uid: string
  type: string
}

const readPlans = async (app: App): Promise<PlanIndexItem[]> => {
  // /api/plan/get 的 index 与 data 是同级字段；post 会解包成 data 读不到，必须走 postFull
  const response = await app.api.postFull<{ index?: PlanIndexItem[] }>('/api/plan/get', {})
  return Array.isArray(response.index) ? response.index : []
}

const deleteAllPlans = async (app: App) => {
  // 不吞异常：删不掉就让它响，否则残留计划会让后面的 @plan 用例看到脏数据
  const remaining = await readPlans(app)
  for (const plan of remaining) {
    await app.api.post('/api/plan/delete', { planId: plan.uid })
  }
  const after = await readPlans(app)
  expect(after, '清理失败：计划数据还在，后面的用例会看到残留').toHaveLength(0)
}

const openCreateMenu = async (page: Page) => {
  await page.getByRole('button', { name: 'New plan' }).click()
  const menu = page.locator('.ant-dropdown-menu')
  await expect(menu).toBeVisible()
  return menu
}

const createPlanOfType = async (page: Page, menuLabel: string) => {
  const menu = await openCreateMenu(page)
  await menu
    .locator('.ant-dropdown-menu-item', { hasText: new RegExp('^' + menuLabel + '$') })
    .click()
}

test.describe('@plan plan management', () => {
  test.afterEach(async ({ app }) => {
    await deleteAllPlans(app)
  })

  test('空状态引导 → 新建计划默认名跟随界面语言 → 改名后刷新仍在 → 删除回到空状态', async ({
    app,
    page,
  }) => {
    await app.goto('/plans')

    // 没有计划时是空状态引导，不是一张空表
    await expect(page.locator('.empty-title')).toHaveText('No plans yet')
    await expect(page.locator('.empty-description')).toHaveText('You have not created any plans')
    await expect(page.locator('.plan-config-card')).toHaveCount(0)

    // 新建下拉把四种计划类型都摆出来，文案是「New <类型>」
    const menu = await openCreateMenu(page)
    const items = menu.locator('.ant-dropdown-menu-item')
    await expect(items).toHaveCount(4)
    await expect(items).toHaveText([
      'New MAA plan',
      'New MaaEnd plan',
      'New BAAH plan',
      'New MSS plan',
    ])
    await items.filter({ hasText: /^New MAA plan$/ }).click()

    // 英文界面的默认计划名必须是英文：默认名会被写进计划数据，不能是写死的中文
    await expect(page.locator('.plan-config-card')).toBeVisible()
    await expect(page.locator('.plan-config-card .plan-title-text')).toHaveText('New MAA plan')
    await expect(page.locator('.plan-name').first()).toHaveText('New MAA plan')
    // 选择器卡片的计数标签跟着计划数走（英文复数形式也要对）
    await expect(page.locator('.plan-selector-card .ant-card-head-title')).toContainText('1 plan')
    // 配置表渲染出来（四种类型的表都是 a-table，最少得有一行）
    await expect(
      page.locator('.config-table-wrapper .ant-table-tbody tr.ant-table-row').first()
    ).toBeVisible()

    // 改名：改名按钮 → 输入框 → 回车，列表和标题同步
    await page.locator('.plan-rename-btn').first().click()
    const renameInput = page.locator('.plan-rename-input')
    await expect(renameInput).toBeVisible()
    await renameInput.fill('E2E renamed plan')
    await renameInput.press('Enter')
    await expect(page.locator('.plan-name').first()).toHaveText('E2E renamed plan')
    await expect(page.locator('.plan-config-card .plan-title-text')).toHaveText('E2E renamed plan')

    // 刷新还在 = 改的是持久化数据。刷新后默认名重算逻辑不能把用户改的名字吞掉
    await page.reload()
    await expect(page.locator('.plan-name').first()).toHaveText('E2E renamed plan', {
      timeout: 20_000,
    })

    await app.evidence('plan-created-and-renamed')

    // 删除当前计划：危险按钮 + 二次确认，删完回到空状态，配置区不残留
    await page.getByRole('button', { name: 'Delete this plan' }).click()
    await page.locator('.ant-popconfirm .ant-btn-primary').click()
    await expect(page.locator('.empty-title')).toHaveText('No plans yet')
    await expect(page.locator('.plan-config-card')).toHaveCount(0)
    expect(await readPlans(app)).toHaveLength(0)
  })

  test('四种计划类型都能创建，并各自渲染出配置表', async ({ app, page }) => {
    await app.goto('/plans')
    await expect(page.locator('.empty-title')).toBeVisible()

    const cases = [
      { menuLabel: 'New MAA plan', name: 'New MAA plan', table: '.config-table-wrapper' },
      { menuLabel: 'New MaaEnd plan', name: 'New MaaEnd plan', table: '.config-table-wrapper' },
      { menuLabel: 'New BAAH plan', name: 'New BAAH plan', table: '.baah-table-wrapper' },
      { menuLabel: 'New MSS plan', name: 'New MSS plan', table: '.config-table-wrapper' },
    ]

    for (const [index, item] of cases.entries()) {
      await createPlanOfType(page, item.menuLabel)
      await expect(page.locator('.plan-name')).toHaveCount(index + 1)
      await expect(page.locator('.plan-config-card .plan-title-text')).toHaveText(item.name)
      // 每种类型的表结构不同，但都该有「设置名 + 至少一行设置项」
      await expect(page.locator(item.table).first()).toBeVisible()
      await expect(
        page.locator(item.table + ' .ant-table-tbody tr.ant-table-row').first()
      ).toBeVisible()
    }

    // 混合类型的计划列表会给每个计划打上类型标签，用户才分得清哪个是哪种
    await expect(page.locator('.plan-type-tag')).toHaveCount(4)
    await app.evidence('plan-all-types')
  })

  test('英文默认名重载后不变回中文，再建同类型不重名', async ({ app, page }) => {
    // 回归：重载路径曾不传翻译函数，把已保存的英文默认名重算成中文兜底名，
    // 显示跟着回退，且按列表名的重名判断失效，第二次又存出同名计划（PR #1627 审查）
    await app.goto('/plans')
    await expect(page.locator('.empty-title')).toBeVisible()

    await createPlanOfType(page, 'New MAA plan')
    await expect(page.locator('.plan-name').first()).toHaveText('New MAA plan')

    // 离开再回来：默认名按当前语言重算，仍是当初保存的英文，不变回中文
    await page.reload()
    await expect(page.locator('.plan-name').first()).toHaveText('New MAA plan', {
      timeout: 20_000,
    })

    // 再建同类型：重名判断对真实列表名工作，第二个带后缀而不是再次同名
    await createPlanOfType(page, 'New MAA plan')
    await expect(page.locator('.plan-name')).toHaveCount(2)
    const names = await page.locator('.plan-name').allTextContents()
    expect(new Set(names).size).toBe(2)
    expect(names[1]).toMatch(/^New MAA plan \d+$/)
  })
})
