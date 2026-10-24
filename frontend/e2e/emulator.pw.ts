import { expect, test } from './fixtures'

const backendBaseUrl = () => `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`

type EmulatorIndexEntry = { uid: string; type: string }

type App = { api: { raw: import('@playwright/test').APIRequestContext } }

/** 直接问后端要模拟器配置列表：页面上看不出这条配置是谁造的。 */
const readEmulatorIndex = async (app: App): Promise<EmulatorIndexEntry[]> => {
  const response = await app.api.raw.post(`${backendBaseUrl()}/api/emulator/get`, { data: {} })
  const body = (await response.json()) as { code: number; index?: EmulatorIndexEntry[] }
  expect(body.code, '查询模拟器配置列表失败').toBe(200)
  return body.index ?? []
}

const expectNoEmulatorConfig = async (app: App) => {
  expect(
    (await readEmulatorIndex(app)).map(entry => entry.uid),
    '模拟器页不是空状态：有别的用例留下了配置（造数据的用例必须在 finally 里删掉）'
  ).toEqual([])
}

test.describe('@emulator config', () => {
  // 新用户第一次进模拟器页时页面是空的：只说「暂无数据」等于没说，必须告诉他下一步做什么。
  test('空状态说明能做什么，并且两种添加入口都在', async ({ app, page }) => {
    await expectNoEmulatorConfig(app)
    await app.goto('/emulators')

    const empty = page.locator('.empty-state-large')
    await expect(empty).toBeVisible()
    await expect(empty).toContainText('No emulator configuration yet')
    await expect(empty.getByRole('button', { name: 'Search for emulators' })).toBeVisible()
    await expect(empty.getByRole('button', { name: 'Add manually' })).toBeVisible()
    await app.evidence('emulator-empty-state')
  })

  // 手动添加不依赖本机装没装模拟器，是用户真正走得通的一条路：加完能改名、刷新还在、删掉能回到空状态。
  test('手动添加后能改名，刷新仍在，删除后回到空状态', async ({ app, page }) => {
    await expectNoEmulatorConfig(app)

    try {
      await app.goto('/emulators')
      await page.getByRole('button', { name: 'Add manually' }).click()

      // 默认名要跟随界面语言：后端 default_factory 是中文「新模拟器」，英文界面不该看到它
      const tabTitle = page.locator('.emulator-tabs .tab-title').first()
      await expect(tabTitle).toHaveText('New emulator')

      // 名字是即时保存的（blur 触发 /api/emulator/update），先挂等待再填
      const saveResponse = page.waitForResponse(
        response =>
          response.url().endsWith('/api/emulator/update') &&
          response.request().method() === 'POST' &&
          response.ok()
      )
      const nameInput = page.getByPlaceholder('Enter a name')
      await expect(nameInput).toHaveValue('New emulator')
      await nameInput.fill('E2E emulator')
      await nameInput.blur()
      await saveResponse
      await expect(tabTitle).toHaveText('E2E emulator')

      // hash 路由来回切读的是内存数据，只有整页刷新才验证到真的落盘
      await page.reload()
      await expect(page.locator('.emulator-tabs .tab-title').first()).toHaveText('E2E emulator')
      await app.evidence('emulator-renamed')

      // 按钮的可访问名是「图标 alt + 文案」= 'delete Delete'，不能用 exact 精确匹配
      await page
        .locator('.config-section')
        .getByRole('button', { name: /Delete/ })
        .click()
      await page.locator('.ant-popconfirm .ant-btn-primary').click()
      await expect(page.locator('.empty-state-large')).toBeVisible()
    } finally {
      for (const entry of await readEmulatorIndex(app)) {
        await app.api.post('/api/emulator/delete', { emulatorId: entry.uid })
      }
      expect(
        await readEmulatorIndex(app),
        '清理失败：模拟器配置还在，后面的用例会看到残留'
      ).toEqual([])
    }
  })
})
