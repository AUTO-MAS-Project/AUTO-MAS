import { expect, test } from './fixtures'

/**
 * 英文界面下的中文泄漏巡检。
 *
 * 判据只有一条：界面语言是英文时，页面上不该出现汉字。这里只查汉字
 * （Han），不查全角标点——引号、破折号这类字符在英文文案里也可能是全角，
 * 会把真实泄漏埋进噪声里。
 *
 * 白名单是**棘轮**：只能删不能加。新增一条就等于承认英文界面上永久留着
 * 一句中文，必须在 reason 里写清为什么暂时留。
 *
 * 汉字判据的正则写在下面 scanCjk 的 page.evaluate 里：evaluate 在浏览器
 * 上下文执行，捕获不到外面的常量，只能内联一份。
 */

/** 允许出现汉字的地方：{ route, text, reason } */
const LEARN_ALLOWLIST: Array<{ route: string; text: string; reason: string }> = []

/** 逐条路由扫描页面上带汉字的文本节点，返回去重后的命中列表。 */
const scanCjk = async (
  page: import('@playwright/test').Page
): Promise<Array<{ text: string; tag: string; cls: string }>> =>
  page.evaluate(() => {
    const cjk = /[\u3400-\u4dbf\u4e00-\u9fff]/
    const skip = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA'])
    const out: Array<{ text: string; tag: string; cls: string }> = []
    const seen = new Set<string>()
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const raw = node.textContent?.trim()
      if (!raw || !cjk.test(raw)) continue
      const parent = node.parentElement
      if (!parent || skip.has(parent.tagName)) continue
      if (parent.closest('[aria-hidden="true"], .log-editor, .monaco-editor')) continue
      // 取到组件里最近的可见容器，报错时能直接定位到是哪一块
      const host = parent.closest('[class]') ?? parent
      const key = raw.slice(0, 60)
      if (seen.has(key)) continue
      seen.add(key)
      out.push({
        text: key,
        tag: parent.tagName.toLowerCase(),
        cls: typeof host.className === 'string' ? host.className.slice(0, 80) : '',
      })
    }
    return out
  })

const ROUTES = [
  '/home',
  '/scheduler',
  '/settings',
  '/settings/mystery',
  '/logs',
  '/scripts',
  '/plans',
  '/emulators',
  '/queue',
  '/history',
  '/gamesign',
  '/theme-store',
]

test.describe('界面语言', { tag: '@i18n' }, () => {
  for (const route of ROUTES) {
    test(`${route} 在英文界面下没有中文泄漏`, async ({ app, page }) => {
      await app.goto(route)

      // 先确认页面真的渲染出来了：白板页面上「没有中文」是假通过
      await expect
        .poll(async () => (await page.locator('body').innerText()).length, { timeout: 15_000 })
        .toBeGreaterThan(40)

      const hits = await scanCjk(page)
      const allowed = LEARN_ALLOWLIST.filter(entry => entry.route === route)
      const unexpected = hits.filter(hit => !allowed.some(entry => hit.text.includes(entry.text)))

      if (unexpected.length) {
        await app.evidence(`cjk-leak${route.replace(/\//g, '-')}`)
        await test.info().attach(`cjk-${route.replace(/\//g, '-')}.json`, {
          contentType: 'application/json',
          body: JSON.stringify({ route, unexpected, allowed, hits }, null, 2),
        })
      }

      expect(
        unexpected,
        `${route} 在英文界面下出现了中文：\n` +
          unexpected
            .map(hit => `  · [${hit.tag}${hit.cls ? '.' + hit.cls : ''}] ${hit.text}`)
            .join('\n')
      ).toEqual([])
    })
  }

  test('切换界面语言后调度台标题跟着变', async ({ app, page }) => {
    // 语言存在前端配置里（浏览器模式下是 localStorage），改完必须重载才生效
    await page.addInitScript(() => {
      // 浏览器预览把前端配置存在这个键里（见 src/utils/browserDevElectronAPI.ts）
      const key = 'auto-mas.browser-dev.config'
      const raw = window.localStorage.getItem(key)
      const parsed = raw ? JSON.parse(raw) : {}
      // addInitScript 每次导航都会跑，包括用例中途的 reload；
      // 已经写过语言就不再覆盖，否则「切到英文后 reload」会被这一步重置回中文。
      if (parsed.language) return
      window.localStorage.setItem(key, JSON.stringify({ ...parsed, language: 'zh-CN' }))
    })
    await app.goto('/scheduler')
    await expect(page.locator('.tab-title').first()).toContainText('主运行面板')

    await page.evaluate(() => {
      const key = 'auto-mas.browser-dev.config'
      const parsed = JSON.parse(window.localStorage.getItem(key) ?? '{}')
      window.localStorage.setItem(key, JSON.stringify({ ...parsed, language: 'en-US' }))
    })
    await page.reload()
    await expect(page.locator('.tab-title').first()).toContainText('Main run panel')
  })
})
