import { expect, test } from './fixtures'

/**
 * 全路由巡检：把应用里每一条可直达的路由都走一遍，断言「页面真的渲染出来了」。
 *
 * 为什么要有这个文件：其余业务用例只覆盖被驱动的几条主流程，
 * 一条路由白屏、渲染崩了、页头文案丢了，都不影响那些用例通过。
 * 这里给每条路由单独一条用例：谁坏了，报告里就是谁的名字，且自带该路由的诊断附件。
 *
 * 断言口径（每条路由都要过）：
 * 1. 落地 hash 符合预期（重定向本身就是被测行为）；
 * 2. 没有 Vite 编译错误浮层（由 app.goto 抛错）；
 * 3. 页头文案 / 结构元素 / 正文文案至少各有一条命中；
 * 4. 非独立窗口页面必须渲染出侧边栏（AppLayout 挂上了才算页面成型）；
 * 5. 用例结束时的控制台报错、未捕获异常、请求失败、服务端 5xx 由 fixtures 兜底判失败。
 *
 * 新增路由时：同步在下面的 ROUTE_CASES 里加一条，
 * harness.check.mjs 会对照 frontend/src/router/index.ts 检查是否漏了。
 */
type RouteCase = {
  /** 浏览器地址栏里敲的 hash 路由 */
  path: string
  /** 落地后应停留的 hash；不填即等于 path。重定向路由必填 */
  expectHash?: string
  /** 页头文案（en-US）。用页头而不是整页文本，避免命中侧边栏同名项 */
  heading?: string
  /** 正文里必须出现的文案 */
  text?: string
  /** 必须可见的结构元素 */
  selector?: string
  /** 独立窗口页面：不挂 AppLayout，没有侧边栏 */
  standalone?: boolean
}

const ROUTE_CASES: RouteCase[] = [
  { path: '/home', heading: 'welcome to AUTO-MAS', selector: '.home-page' },
  { path: '/scripts', heading: 'Managed scripts' },
  { path: '/plans', heading: 'Plans', selector: '.plans-main' },
  { path: '/emulators', heading: 'Emulators' },
  { path: '/queue', heading: 'Queues', selector: '.queue-main' },
  { path: '/scheduler', heading: 'Scheduler', selector: '.scheduler-main' },
  { path: '/history', heading: 'History', selector: '.history-page' },
  { path: '/taskboard', heading: 'Taskboard' },
  { path: '/gamesign', heading: 'Game Community' },
  // 这两个是旧链接的兼容重定向，落地位置就是它们的契约
  { path: '/gamesign/sign', expectHash: '#/gamesign', heading: 'Game Community' },
  {
    path: '/gamesign/activity',
    expectHash: '#/gamesign?tab=activity',
    heading: 'Game Community',
  },
  { path: '/theme-store', heading: 'Resource store' },
  { path: '/settings', heading: 'Settings' },
  // 神秘入口未解锁时是一张解锁卡，标题走 i18n，不能作为英文文案断言
  { path: '/settings/mystery', selector: '.mystery-unlock' },
  { path: '/logs', standalone: true, text: 'Backend log' },
  // 开发模式免初始化门禁，/initialization 会直接落到主页
  { path: '/initialization', expectHash: '#/home', heading: 'welcome to AUTO-MAS' },
  // 虚拟显示器询问窗口：内容随后端状态变化，只要求它别白屏
  { path: '/vdd-prompt', standalone: true },
]

const header = (page: import('@playwright/test').Page) =>
  page.locator('h1, .page-title, .home-title, .ant-card-head-title').first()

test.describe('@routes 全路由巡检', () => {
  for (const routeCase of ROUTE_CASES) {
    test(`${routeCase.path} 能正常渲染`, async ({ app, page }) => {
      await app.goto(routeCase.path, { expectHash: routeCase.expectHash })

      if (routeCase.standalone !== true) {
        // 侧边栏是 AppLayout 的锚点：它没出来就说明落到了「半截页面」
        await expect(page.locator('.ant-menu').first()).toBeVisible()
      }

      if (routeCase.heading) {
        // 首页问候语随时段变化（"Good afternoon — welcome…" / "Working late? Welcome…"），
        // 大小写也不同，所以用忽略大小写的正则，别把时段文案锁死
        await expect(header(page)).toContainText(
          new RegExp(
            routeCase.heading.replace(
              /[.*+?^${}()|[\]\\]/g,
              '\\        await expect(header(page)).toContainText(routeCase.heading)'
            ),
            'i'
          )
        )
      }
      if (routeCase.selector) {
        await expect(page.locator(routeCase.selector).first()).toBeVisible()
      }
      if (routeCase.text) {
        await expect(page.getByText(routeCase.text, { exact: false }).first()).toBeVisible()
      }

      // 兜底：页面不许是白板。懒加载分包慢一点时一次性读 innerText 会拿到 0，
      // 像 toBeVisible 一样给它重试的余地（/vdd-prompt、/logs 都踩过这个坑）。
      await expect
        .poll(
          async () => (await page.locator('#app').innerText()).replace(/\s+/g, ' ').trim().length,
          { timeout: 15_000, message: `${routeCase.path} 渲染出来的正文一直是空的` }
        )
        .toBeGreaterThan(40)

      await app.evidence(`route${routeCase.path.replace(/\//g, '-')}`)
    })
  }
})
