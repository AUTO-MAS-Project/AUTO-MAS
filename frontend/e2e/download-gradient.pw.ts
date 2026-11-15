import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test, expect } from './fixtures'

test('@scheduler prefetch stays in the log header while script logs append', async ({
  app,
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem('log-highlight-styles', JSON.stringify({ downloadGradient: true }))
  })
  await app.goto('/TestRouter')
  const panel = page.locator('.demo-log-panel')
  const header = panel.locator('.scheduler-panel-header')
  const packageName = header.locator('.download-log-package')
  const packageText = async () => (await packageName.allTextContents()).join('')
  await expect.poll(packageText, { timeout: 20_000 }).toBe('MaaEnd-update-win-x86_64.zip')
  const methodText = async () =>
    (await header.locator('.download-log-method').allTextContents()).join('')
  await expect.poll(methodText).toBe('[FluxDown]')
  const progressText = async () =>
    (await header.locator('.download-log-progress').allTextContents()).join('')
  const first = await progressText()
  await expect.poll(progressText).not.toBe(first)
  await expect(panel.locator('.monaco-editor')).toContainText('理智作战运行中')
  await expect(panel.locator('.monaco-editor')).not.toContainText('MaaEnd-update')
  await expect(panel.locator('.monaco-editor [class*="download-log-"]')).toHaveCount(0)
  await page.locator('.method-select').click()
  await page.locator('.method-select').getByRole('combobox').press('ArrowUp')
  await page.locator('.method-select').getByRole('combobox').press('Enter')
  await expect.poll(methodText).toBe('[httpx]')
  await expect(header.locator('.download-log-animated')).toBeVisible()
  await app.evidence('prefetch-current-scheduler-panel')
})

test('@scheduler download text keeps its gradient phase on the first paint after replacement', async ({
  page,
}) => {
  const css = await readFile(path.join(__dirname, '../src/components/downloadLog.css'), 'utf8')
  await page.setContent(`<style>${css}</style>
    <div class="download-log-styled download-log-animated" style="--download-period:1s; --download-package-gradient:linear-gradient(90deg,red,blue,red)">
      <span class="download-log-package">MaaEnd-update.zip · 42%</span>
    </div>`)
  const phases = await page.evaluate(async () => {
    const wrapper = document.querySelector('.download-log-styled')!
    const text = wrapper.querySelector('span')!
    // 两种实现都停在相同的动画中途，再模拟 Monaco 的文字节点替换。
    await Promise.all(wrapper.getAnimations({ subtree: true }).map(animation => animation.ready))
    for (const animation of wrapper.getAnimations({ subtree: true })) {
      animation.pause()
      animation.currentTime = 500
    }
    const before = getComputedStyle(text).backgroundPositionX
    const replacement = text.cloneNode(true) as HTMLElement
    replacement.textContent = 'MaaEnd-update.zip · 43%'
    text.replaceWith(replacement)
    const firstPaint = getComputedStyle(replacement).backgroundPositionX
    for (const animation of wrapper.getAnimations({ subtree: true })) animation.play()
    await new Promise<void>(resolve =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    )
    return { before, firstPaint, running: getComputedStyle(replacement).backgroundPositionX }
  })
  expect(phases.before).not.toBe('0%')
  expect(phases.firstPaint).toBe(phases.before)
  expect(phases.running).not.toBe(phases.firstPaint)
})

test('@scheduler prefetch leaves logs and controls visible in a narrow scheduler pane', async ({
  app,
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      'auto-mas.browser-dev.config',
      JSON.stringify({ language: 'ja-JP', themeMode: 'light' })
    )
  })
  const prefetch = {
    target: 'MaaEnd',
    status: '下载中',
    method: 'FluxDown',
    package: 'MaaEnd-update-win-x86_64.zip',
    progress: '42.0%',
    size: '84.0/200.0 MiB',
    rate: '5.2 MiB/s',
  }
  const task = {
    info: { name: 'Narrow header', mode: 'AutoProxy', status: 'running', trigger: 'manual' },
    current: { index: 'script-run', prefetch },
    scripts: {
      order: [{ uid: 'script-run', type: 'TaskScriptItem' }],
      data: {
        'script-run': {
          info: { script_id: 'script-config', name: 'MAA', status: '运行' },
          users: { order: [], data: {} },
        },
      },
    },
  }
  await page.route('**/api/dispatch/runtime-snapshot', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify({
        tasks: [
          {
            taskId: 'ab771126-0a99-4d87-8232-6d5ddcc46289',
            task,
            mode: 'AutoProxy',
            trigger: 'manual',
            scripts: [{ scriptId: 'script-config', scriptType: 'MaaConfig' }],
            stopping: false,
            log: Array.from({ length: 60 }, (_, index) => `Test log ${index + 1}\n`).join(''),
            logSeq: 1,
            logFirstLine: 1,
          },
        ],
      }),
    })
  })
  await page.setViewportSize({ width: 1000, height: 900 })
  await app.goto('/scheduler')
  const panel = page.locator('.log-panel:visible')
  await expect(panel.locator('.download-log-package')).toHaveText(prefetch.package)
  await expect(panel.locator('.monaco-editor')).toContainText('Test log 60')
  for (const locale of ['ja-JP', 'zh-CN', 'en-US']) {
    await page.setViewportSize({ width: 1000, height: 900 })
    await page.evaluate(async locale => {
      const module = '/src/composables/useLocale.ts'
      const { useLocale } = await import(module)
      await useLocale().setLocale(locale)
    }, locale)
    for (const mode of ['browse', 'follow']) {
      await page.setViewportSize({ width: 1000, height: 900 })
      const button = panel.locator('.log-controls button')
      if ((mode === 'follow') !== ((await button.getAttribute('aria-pressed')) === 'true')) {
        await button.click()
      }
      for (const width of [800, 769, 768]) {
        await page.setViewportSize({ width, height: 900 })
        await expect
          .poll(() =>
            panel.evaluate(element => {
              const panel = element.getBoundingClientRect()
              const controls = element.querySelector('.log-controls')!.getBoundingClientRect()
              const content = element.querySelector('.log-content')!.getBoundingClientRect()
              return {
                logsVisible: content.height > 0 && content.bottom <= panel.bottom,
                controlsVisible:
                  controls.top >= panel.top &&
                  controls.bottom <= panel.bottom &&
                  controls.right <= panel.right,
              }
            })
          )
          .toEqual({ logsVisible: true, controlsVisible: true })
        if (mode === 'follow') {
          await expect(panel.locator('.monaco-editor')).toContainText('Test log 60')
        }
      }
    }
  }
  await app.evidence('prefetch-narrow-scheduler')
})
