import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test, expect } from './fixtures'

test('@scheduler prefetch stays after appending logs in the current log panel', async ({
  app,
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem('log-highlight-styles', JSON.stringify({ downloadGradient: true }))
  })
  await app.goto('/TestRouter')
  const panel = page.locator('.demo-log-panel')
  const packageName = panel.locator('.download-log-package')
  const packageText = async () => (await packageName.allTextContents()).join('')
  await expect.poll(packageText, { timeout: 20_000 }).toBe('MaaEnd-update-win-x86_64.zip')
  const methodText = async () =>
    (await panel.locator('.download-log-method').allTextContents()).join('')
  await expect.poll(methodText).toBe('[FluxDown]')
  const progressText = async () =>
    (await panel.locator('.download-log-progress').allTextContents()).join('')
  const first = await progressText()
  await expect.poll(progressText).not.toBe(first)
  const logText = (await panel.locator('.view-lines').textContent())!
  expect(logText.lastIndexOf('MaaEnd-update')).toBeGreaterThan(
    logText.lastIndexOf('理智作战运行中')
  )
  await expect(panel.locator('.monaco-editor')).toContainText('理智作战运行中')
  await page.locator('.method-select').click()
  await page.locator('.method-select').getByRole('combobox').press('ArrowUp')
  await page.locator('.method-select').getByRole('combobox').press('Enter')
  await expect.poll(methodText).toBe('[httpx]')
  await expect(panel.locator('.download-log-animated')).toBeVisible()
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
