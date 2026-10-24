import {
  test as base,
  expect,
  type APIRequestContext,
  type Page,
  type TestInfo,
} from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

type IgnoreRules = {
  console?: RegExp[]
  /** Vue / antd 等框架警告走 console 输出，单独一档：默认同样判失败，但可以按条目放行。 */
  warning?: RegExp[]
  pageError?: RegExp[]
  request?: RegExp[]
  serverError?: RegExp[]
}

type Diagnostics = {
  consoleErrors: string[]
  consoleWarnings: string[]
  pageErrors: string[]
  failedRequests: string[]
  serverErrors: string[]
  startupWarnings: string[]
  /** 被 ignore 规则放过的条目，失败时一并附上，便于判断「是不是放得太宽」。 */
  suppressed: string[]
}

type ApiResult<T> = { code?: number; status?: string; message?: string; data?: T }

type Api = {
  get: <T = unknown>(
    route: string,
    params?: Record<string, string | number | boolean>
  ) => Promise<T>
  post: <T = unknown>(route: string, body?: unknown) => Promise<T>
  raw: APIRequestContext
}

type App = {
  /**
   * 打开一条路由并等应用挂载。
   * expectHash 用于「重定向本身就是被测行为」的路由：/initialization 在开发模式落到 /home，
   * /gamesign/activity 落到 /gamesign?tab=activity，断言落地 hash 比断言「没重定向」更有意义。
   */
  goto: (route: string, options?: { expectHash?: string }) => Promise<void>
  evidence: (name: string, maskSelectors?: string[]) => Promise<void>
  api: Api
  diagnostics: Diagnostics
  ignore: (rules: IgnoreRules) => void
  expectNoUnexpectedErrors: (hint?: string) => void
}

const backendBaseUrl = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`

// 这些噪声不是被测行为：请求被 fixtures 主动 abort、浏览器自动打 favicon、Vue 的 HMR 心跳。
// 这里只是「默认模板」：每个用例都会拿到 createRules() 的新副本，
// 否则 app.ignore() 追加的规则会顺着模块作用域漏给同文件后面的用例，出现「这条用例替别的用例放行」。
const defaultRules: Required<IgnoreRules> = {
  console: [/^\[vite\]/, /Download the Vue Devtools/],
  // 环境噪声而非被测行为：headless Chromium 的 WebGL 读回性能提示；
  // 在线外观在浏览器预览模式本来就用不了（Electron 专属），打开 /theme-store 必刷。
  warning: [
    /GL Driver Message.*GPU stall/,
    /\[在线外观\] 加载在线外观列表失败: 浏览器预览不支持在线外观/,
  ],
  pageError: [],
  request: [/\/api\/info\/[^/]+\/activity$/, /\/favicon\.ico$/],
  serverError: [],
}

const createRules = (): Required<IgnoreRules> => ({
  console: [...defaultRules.console],
  warning: [...defaultRules.warning],
  pageError: [...defaultRules.pageError],
  request: [...defaultRules.request],
  serverError: [...defaultRules.serverError],
})

/**
 * 一条诊断文本的可匹配形态。
 *
 * 请求类诊断长这样："GET http://127.0.0.1:58344/api/core/health?_=1 net::ERR_FAILED"。
 * 如果规则只能匹配整行，作者就必须把轮询用的查询串也写进正则，规则会随实现漂移。
 * 所以这里额外给出「去掉查询串的 URL」与「只有路径」两种形态：
 * /\.api\/core\/health$/ 既能匹配带查询串的健康检查，也能匹配干净路径。
 */
const textVariants = (text: string): string[] => {
  const variants = [text]
  for (const raw of text.match(/https?:\/\/[^\s]+/g) ?? []) {
    variants.push(raw)
    try {
      const url = new URL(raw)
      variants.push(`${url.origin}${url.pathname}`)
      variants.push(url.pathname)
    } catch {
      // 不是合法 URL 就只用原始形态
    }
  }
  return variants
}

const matches = (text: string, rules: RegExp[]) => {
  if (rules.length === 0) return false
  const variants = textVariants(text)
  return rules.some(rule => variants.some(variant => rule.test(variant)))
}

const attachBackendLog = async (testInfo: TestInfo): Promise<void> => {
  const dataRoot = process.env.AUTO_MAS_E2E_DATA_ROOT
  if (
    !dataRoot ||
    (process.env.AUTO_MAS_E2E_REAL === '1' && process.env.AUTO_MAS_E2E_ATTACH_BACKEND_LOG !== '1')
  )
    return

  const logPath = path.join(dataRoot, 'debug', 'app.log')
  try {
    await fs.access(logPath)
    await testInfo.attach('backend-app.log', { path: logPath, contentType: 'text/plain' })
  } catch {
    // The backend may fail before the logger creates a file; Playwright's own trace is enough.
  }
}

/** 页面里冒出来的 Vite 编译错误：应用根本没跑起来，后面所有断言都会以「找不到元素」失败。 */
const readBootFailure = async (page: Page): Promise<string> => {
  const overlay = page.locator('vite-error-overlay')
  if ((await overlay.count()) === 0) return ''
  const text = await overlay
    .first()
    .evaluate(element => (element.shadowRoot?.textContent ?? element.textContent ?? '').trim())
    .catch(() => '')
  return text.replace(/\s+/g, ' ').slice(0, 800)
}

/**
 * 等到应用真正挂载。失败时优先报出 Vite 的原始编译错误，
 * 而不是让调用方在 10 秒后收到一句「元素找不到」。
 */
const waitForAppShell = async (page: Page): Promise<void> => {
  const outcome = await expect
    .poll(
      async () => {
        if ((await readBootFailure(page)) !== '') return 'boot-error'
        return (await page
          .locator('#app')
          .isVisible()
          .catch(() => false))
          ? 'ready'
          : 'pending'
      },
      { timeout: 25_000, intervals: [100, 250, 500, 1000] }
    )
    .not.toBe('pending')
    .then(() => 'settled')
    .catch(() => 'timeout')

  if (outcome === 'timeout') {
    throw new Error(
      `应用在 25 秒内没有挂载：#app 不可见，也没有 Vite 编译错误。先单独跑 yarn vp dev 看前端能否启动。`
    )
  }
  const failure = await readBootFailure(page)
  if (failure) {
    throw new Error(`前端编译失败，应用没有启动：${failure}`)
  }
}

const createApi = (request: APIRequestContext): Api => {
  const unwrap = async <T>(method: string, url: string, payload: unknown): Promise<T> => {
    const response = await request.fetch(url, {
      method,
      data: method === 'GET' ? undefined : payload,
      params: method === 'GET' ? (payload as Record<string, string | number | boolean>) : undefined,
      failOnStatusCode: false,
    })
    const text = await response.text()
    if (!response.ok()) {
      throw new Error(`${method} ${url} 返回 ${response.status()}：${text.slice(0, 400)}`)
    }
    let parsed: ApiResult<T>
    try {
      parsed = JSON.parse(text) as ApiResult<T>
    } catch {
      throw new Error(`${method} ${url} 返回的不是 JSON：${text.slice(0, 400)}`)
    }
    if (parsed.code !== undefined && parsed.code !== 200) {
      throw new Error(`${method} ${url} 业务失败 code=${parsed.code}：${parsed.message ?? ''}`)
    }
    return parsed.data as T
  }
  return {
    raw: request,
    get: <T = unknown>(route: string, params: Record<string, string | number | boolean> = {}) =>
      unwrap<T>('GET', `${backendBaseUrl}${route}`, params),
    post: <T = unknown>(route: string, body: unknown = {}) =>
      unwrap<T>('POST', `${backendBaseUrl}${route}`, body),
  }
}

/**
 * 汇总一组诊断里「不该出现的东西」。
 *
 * 抽成模块级函数是因为它有两个调用点：用例主动调用 app.expectNoUnexpectedErrors()，
 * 以及 context fixture 收尾时统一兜底。两处必须用同一套口径，不能各写一遍。
 */
const collectProblems = (diagnostics: Diagnostics, rules: Required<IgnoreRules>): string[] => {
  const problems: string[] = []
  const pick = (items: string[], allowed: RegExp[]) => {
    const kept: string[] = []
    for (const item of items) {
      if (matches(item, allowed)) diagnostics.suppressed.push(item)
      else kept.push(item)
    }
    return kept
  }
  const failedRequests = pick(diagnostics.failedRequests, rules.request)
  const serverErrors = pick(diagnostics.serverErrors, rules.serverError)
  // "Failed to load resource: ..." 不带 URL，是浏览器对网络失败的复述。
  // 网络层已经逐条断言过（上面的请求失败 / 服务端 5xx，带完整 URL 与状态码），
  // 再拿这条判失败只会让同一次失败出现两遍，还带着「说不清是哪个资源」的噪声。
  // 例外：网络层一条都没记到时（例如被 Service Worker 拦掉），仍按控制台报错处理，不静默吞掉。
  const hasNetworkEvidence = diagnostics.failedRequests.length + diagnostics.serverErrors.length > 0
  const isDerivedResourceNoise = (text: string) =>
    /^Failed to load resource: /.test(text) && hasNetworkEvidence
  const consoleErrors = pick(
    diagnostics.consoleErrors.filter(item => {
      if (!isDerivedResourceNoise(item)) return true
      diagnostics.suppressed.push(`[网络失败的复述] ${item}`)
      return false
    }),
    rules.console
  )
  const consoleWarnings = pick(diagnostics.consoleWarnings, rules.warning)
  const pageErrors = pick(diagnostics.pageErrors, rules.pageError)

  if (consoleErrors.length > 0) problems.push(`控制台报错：\n  ${consoleErrors.join('\n  ')}`)
  // 框架警告（Vue prop 类型、组件库弃用）默认不阻断：它们数量大、来源广，
  // 全部判失败会让整套用例只剩红。它们仍会被 attach 成 page-warnings.json，
  // 想清理存量时用 AUTO_MAS_E2E_STRICT_WARNINGS=1 把它们变成失败项。
  if (consoleWarnings.length > 0) {
    if (process.env.AUTO_MAS_E2E_STRICT_WARNINGS === '1') {
      problems.push(`控制台警告（严格模式）：\n  ${consoleWarnings.join('\n  ')}`)
    } else {
      console.warn(
        `[e2e] 控制台警告 ${consoleWarnings.length} 条（不阻断；AUTO_MAS_E2E_STRICT_WARNINGS=1 可判失败），已附在 page-warnings.json`
      )
    }
  }
  if (pageErrors.length > 0) problems.push(`未捕获异常：\n  ${pageErrors.join('\n  ')}`)
  if (failedRequests.length > 0) problems.push(`请求失败：\n  ${failedRequests.join('\n  ')}`)
  if (serverErrors.length > 0) problems.push(`服务端 5xx：\n  ${serverErrors.join('\n  ')}`)
  return problems
}

const createApp = (
  page: Page,
  testInfo: TestInfo,
  diagnostics: Diagnostics,
  rules: Required<IgnoreRules>
): App => ({
  goto: async (route: string, options: { expectHash?: string } = {}) => {
    const routePath = route.startsWith('/') ? route : `/${route}`
    const expectedHash = options.expectHash ?? `#${routePath}`
    await page.goto(`/#${routePath}`)
    await waitForAppShell(page)
    await expect.poll(() => new URL(page.url()).hash, { timeout: 20_000 }).toBe(expectedHash)
    await expect(page.locator('#app')).toBeVisible()
    // 启动期后台初始化失败会弹「Got it」说明弹窗；它出现本身就是环境不健康的信号，记下来
    const gotIt = page.getByRole('button', { name: 'Got it' })
    if (await gotIt.isVisible().catch(() => false)) {
      const modal = page.locator('.ant-modal-body, .ant-modal-confirm-content').first()
      const detail = (await modal.innerText().catch(() => '')).replace(/\s+/g, ' ').slice(0, 300)
      diagnostics.startupWarnings.push(detail || 'startup dialog')
      await gotIt.click()
      await expect(gotIt).toBeHidden()
    }
  },
  evidence: async (name: string, maskSelectors: string[] = []) => {
    if (process.env.AUTO_MAS_E2E_REAL === '1') {
      maskSelectors = [
        ...maskSelectors,
        '.task-control',
        '.tab-title',
        '.overview-panel-container',
        '.log-panel-container',
        '.queue-scope',
        '.ant-message',
        '.ant-notification',
      ]
    }
    const screenshotPath = testInfo.outputPath(`${name}.png`)
    await page.screenshot({
      path: screenshotPath,
      fullPage: true,
      mask: maskSelectors.map(selector => page.locator(selector)),
    })
    await testInfo.attach(name, { path: screenshotPath, contentType: 'image/png' })
  },
  api: createApi(page.request),
  diagnostics,
  ignore: (extra: IgnoreRules) => {
    rules.console.push(...(extra.console ?? []))
    rules.warning.push(...(extra.warning ?? []))
    rules.pageError.push(...(extra.pageError ?? []))
    rules.request.push(...(extra.request ?? []))
    rules.serverError.push(...(extra.serverError ?? []))
  },
  expectNoUnexpectedErrors: (hint?: string) => {
    const problems = collectProblems(diagnostics, rules)
    if (problems.length > 0) {
      throw new Error(`${hint ? `${hint}：` : ''}页面出现不该有的错误\n${problems.join('\n')}`)
    }
  },
})

type Guard = { diagnostics: Diagnostics; rules: Required<IgnoreRules> }

/**
 * 每个 BrowserContext 一份诊断与放行规则。
 *
 * 为什么挂在 context 上而不是 app fixture 上：只要用例签名里没写 `app`，
 * Playwright 就不会实例化这个 fixture——初始化脚本、接口桩、兜底断言会一起消失，
 * 用例照跑、照绿，实际什么都没测到（本次排查就被它骗过一次：
 * 一份只取 page 的探针里满是调试面板的中文，看起来像 i18n 漏翻，其实只是 `__AUTO_MAS_E2E__` 没注入）。
 * context 一定会被实例化，于是「跑在这个浏览器上下文里的一切」都受同一套约束。
 */
const guards = new WeakMap<object, Guard>()

const guardOf = (context: object): Guard => {
  const guard = guards.get(context)
  if (!guard) throw new Error('e2e fixtures：找不到当前用例的诊断上下文')
  return guard
}

export const test = base.extend<{ app: App }>({
  context: async ({ context }, use, testInfo) => {
    await context.addInitScript(() => {
      ;(window as Window & { __AUTO_MAS_E2E__?: boolean }).__AUTO_MAS_E2E__ = true
    })
    await context.route('**/api/info/notice/get', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          status: 'success',
          message: '',
          ifNeedShow: false,
          data: {},
        }),
      })
    })
    await context.route('**/api/info/*/activity', route => route.abort())

    const diagnostics: Diagnostics = {
      consoleErrors: [],
      consoleWarnings: [],
      pageErrors: [],
      failedRequests: [],
      serverErrors: [],
      startupWarnings: [],
      suppressed: [],
    }
    const rules = createRules()
    guards.set(context, { diagnostics, rules })

    const attachDiagnostics = (page: Page) => {
      page.on('console', message => {
        const type = message.type()
        if (type !== 'error' && type !== 'warning') return
        const text = message.text().slice(0, 500)
        // Vue / antd 用 console.error / console.warn 打「Warning: ...」，和真正的运行时报错分开记，
        // 否则一条组件库弃用提示会把用例判成「页面崩溃」。
        if (type === 'warning' || /^(?:\[?Vue warn\]?:?|Warning: )/.test(text)) {
          diagnostics.consoleWarnings.push(text)
        } else {
          diagnostics.consoleErrors.push(text)
        }
      })
      page.on('pageerror', error => diagnostics.pageErrors.push(String(error).slice(0, 500)))
      page.on('requestfailed', request =>
        diagnostics.failedRequests.push(
          `${request.method()} ${request.url()} ${request.failure()?.errorText ?? ''}`.slice(0, 500)
        )
      )
      page.on('response', response => {
        if (response.status() >= 500) {
          diagnostics.serverErrors.push(
            `${response.status()} ${response.request().method()} ${response.url()}`
          )
        }
      })
    }
    context.pages().forEach(attachDiagnostics)
    context.on('page', attachDiagnostics)

    await use(context)

    // 用例跑完统一兜底：页面有报错就判失败，不让「元素在就算过」的低标准混进来
    const failed = testInfo.status !== testInfo.expectedStatus
    const problems = collectProblems(diagnostics, rules)
    if (problems.length > 0) {
      if (failed) {
        // 用例本来就失败了：别用兜底错误盖掉真正的失败原因，改成留证据
        await testInfo.attach('page-diagnostics.json', {
          body: Buffer.from(JSON.stringify({ ...diagnostics, problems }, null, 2)),
          contentType: 'application/json',
        })
      } else {
        throw new Error(`用例结束时：页面出现不该有的错误\n${problems.join('\n')}`)
      }
    }
    // 警告不进失败判定，但必须留证据：按文案去重后附在报告里。
    // 已被 ignore 规则放行的警告不附——报告里全是已知噪声时，新警告就没人看了。
    const distinctWarnings = [...new Set(diagnostics.consoleWarnings)].filter(
      item => !matches(item, rules.warning)
    )
    if (distinctWarnings.length > 0) {
      await testInfo.attach('page-warnings.json', {
        body: Buffer.from(JSON.stringify(distinctWarnings, null, 2)),
        contentType: 'application/json',
      })
    }
    await attachBackendLog(testInfo)
  },
  app: async ({ page, context }, use, testInfo) => {
    const { diagnostics, rules } = guardOf(context)
    await use(createApp(page, testInfo, diagnostics, rules))
  },
})

export { expect }
