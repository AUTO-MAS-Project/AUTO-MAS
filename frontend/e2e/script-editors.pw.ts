import { expect, test } from './fixtures'

/**
 * @editors 脚本编辑页巡检：14 种脚本类型的编辑页各开一次。
 *
 * 为什么单独一个文件：编辑页正文来自后端下发的 config payload，每种类型的结构都不一样，
 * 一个字段改名、一个分组缺默认值，页面就会白屏或只剩标题，而 @routes 只覆盖无参数路由。
 * 这里用接口造一份该类型的脚本，再像用户一样点进它的编辑页，断言标题、表单、返回入口都在。
 *
 * 造的数据在 finally 里删掉：一次 `yarn e2e` 的所有用例共用一个数据根，
 * 残留的脚本会打破别的用例的「空列表」断言。
 */
const EDITORS: Array<{ type: string; segment: string; title: string }> = [
  { type: 'MAA', segment: 'maa', title: 'MAA script configuration' },
  { type: 'SRC', segment: 'src', title: 'SRC script configuration' },
  { type: 'MaaEnd', segment: 'maaend', title: 'MaaEnd script configuration' },
  { type: 'Okww', segment: 'okww', title: 'ok-ww script configuration' },
  { type: 'OkNte', segment: 'oknte', title: 'OK-NTE script configuration' },
  { type: 'HSR', segment: 'hsr', title: 'HSR script configuration' },
  { type: 'BetterGI', segment: 'bettergi', title: 'BetterGI script configuration' },
  { type: 'ZzzOd', segment: 'zzzod', title: 'ZZZ-OD script configuration' },
  { type: 'BAAH', segment: 'baah', title: 'BAAH script configuration' },
  { type: 'Whimbox', segment: 'whimbox', title: 'Whimbox script configuration' },
  { type: 'General', segment: 'general', title: 'General script configuration' },
  // MaaFW 家族三种：标题里带脚本名（默认名是后端造的中文数据），只断言固定后缀
  { type: 'MaaFW', segment: 'maafw', title: 'project configuration' },
  { type: 'M9A', segment: 'm9a', title: 'M9A script configuration' },
  { type: 'MSS', segment: 'mss', title: 'MSS script configuration' },
]

const backendBaseUrl = () =>
  'http://127.0.0.1:' + (process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174')

test.describe('@editors 脚本编辑页', () => {
  for (const editor of EDITORS) {
    test(`${editor.type} 编辑页能加载自己的配置`, async ({ app, page }) => {
      // scripts/add 的 id 在响应顶层而不是 data 字段里，走 raw 读完整响应
      const response = await app.api.raw.post(backendBaseUrl() + '/api/scripts/add', {
        data: { type: editor.type, scriptId: null },
      })
      expect(response.ok()).toBeTruthy()
      const created = (await response.json()) as {
        code: number
        scriptId: string
        message?: string
      }
      expect(created.code, `创建 ${editor.type} 脚本失败：${created.message ?? ''}`).toBe(200)
      expect(created.scriptId).toBeTruthy()
      try {
        await app.goto('/scripts/' + created.scriptId + '/edit/' + editor.segment)

        // 1. 页头是这一类型自己的标题，不是通用兜底，也没有停在加载态
        await expect(page.locator('.config-card .ant-card-head-title').first()).toContainText(
          editor.title
        )

        // 2. 配置表单真的渲染出来了：只有标题、正文空着也算坏
        await expect(page.locator('.ant-form-item').first()).toBeVisible()
        expect(await page.locator('.ant-form-item').count()).toBeGreaterThan(1)

        // 3. 回列表的入口在，用户不会卡死在编辑页
        await expect(page.locator('.breadcrumb-link').first()).toBeVisible()

        await app.evidence('editor-' + editor.segment)
      } finally {
        await app.api.post('/api/scripts/delete', { scriptId: created.scriptId }).catch(() => {})
      }
    })
  }

  test('打开不存在的脚本编辑页时回到列表并给出提示', async ({ app, page }) => {
    // 分享链接 / 收藏夹里的旧链接指向已删除的脚本时用户会遇到这条路径。
    // 这里不能用 app.goto：它会断言落地 hash 等于请求的 hash，而这条流程必定被重定向。
    // 后端目前会把缺失脚本的 KeyError 原样带回，断言兼容现状与未来的友好文案。
    await page.goto('/#/scripts/00000000-0000-4000-8000-000000000000/edit/maa')
    await expect(page.locator('.ant-message').first()).toContainText(
      /KeyError|does not exist|Could not load|Failed to load/i
    )
    await expect.poll(() => new URL(page.url()).hash, { timeout: 10_000 }).toBe('#/scripts')
    await app.evidence('editor-missing-script')
  })

  test('读取脚本配置失败时回到列表并给出提示', async ({ app, page }) => {
    app.ignore({ serverError: [/\/api\/scripts\/get$/] })
    await page.route(/\/api\/scripts\/get$/, route =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ code: 500, status: 'error', message: 'boom', data: null }),
      })
    )
    await page.goto('/#/scripts/00000000-0000-4000-8000-000000000001/edit/maa')
    await expect(page.locator('.ant-message').first()).toContainText(
      /boom|does not exist|Could not load|Failed to load/i
    )
    await expect.poll(() => new URL(page.url()).hash, { timeout: 10_000 }).toBe('#/scripts')
    await app.evidence('editor-load-failed')
  })
})
