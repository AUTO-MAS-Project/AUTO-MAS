import { execFile } from 'node:child_process'
import path from 'node:path'
import { promisify } from 'node:util'
import { _electron as electron, type ElectronApplication } from '@playwright/test'
import { test, expect } from './fixtures'
import type { DesktopMascotData } from '../src/types/desktopMascot'

declare global {
  var mascotE2E: {
    imports: Array<{ success: boolean }>
    errors: string[]
    positions: Array<{ x: number; y: number }>
    snapshot(): DesktopMascotData
    service: {
      setActivity(working: boolean, animate: boolean): void
      showNotice(text: string, reaction?: 'success' | 'failure' | 'stopped', key?: string): void
      setReady(ready: boolean, colors: DesktopMascotData['colors']): void
    }
    cursor(position: { x: number; y: number }): void
    delayDrag(delay: number): void
    select(kind: 'full' | 'bare' | 'static'): void
    preferences(patch: { desktopMascotAnimationPaused?: boolean }): void
    dispose(): void
  }
}

test('@mascot 旧包导入、原生 IPC 与桌宠操作反馈', async ({ request }, testInfo) => {
  test.setTimeout(90000)
  const health = await request.get(
    `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}/api/core/health`
  )
  expect(health.ok()).toBe(true)
  const frontendRoot = path.resolve(__dirname, '..')
  await promisify(execFile)(
    process.execPath,
    [path.join(frontendRoot, 'node_modules/typescript/bin/tsc'), '-p', 'tsconfig.electron.json'],
    { cwd: frontendRoot, windowsHide: true }
  )
  const environment: Record<string, string> = {
    ...Object.fromEntries(
      Object.entries(process.env).filter(
        (entry): entry is [string, string] =>
          entry[1] !== undefined && entry[0] !== 'ELECTRON_RUN_AS_NODE'
      )
    ),
    AUTO_MAS_E2E: '1',
    VITE_DEV_SERVER_URL: `http://127.0.0.1:${process.env.AUTO_MAS_E2E_FRONTEND_PORT ?? '5174'}`,
  }
  let application: ElectronApplication | undefined
  try {
    application = await electron.launch({
      args: [path.join(__dirname, 'fixtures/mascot-main.cjs')],
      env: environment,
    })
    const app = application
    const page = await app.firstWindow()
    const pageErrors: string[] = []
    page.on('pageerror', error => pageErrors.push(error.message))
    const snapshot = () => app.evaluate(() => globalThis.mascotE2E.snapshot())
    const cursor = (x: number, y: number) =>
      app.evaluate((_electron, position) => globalThis.mascotE2E.cursor(position), { x, y })
    const avatar = page.locator('.mascot-avatar')
    const image = page.locator('.mascot-sprite img')
    await expect(image).toBeVisible()
    expect(
      await app.evaluate(() => globalThis.mascotE2E.imports.every(result => result.success))
    ).toBe(true)
    expect((await snapshot()).animation?.frameCount).toBe(4)

    await test.step('点击及阈值内移动不进入拖拽', async () => {
      const box = (await avatar.boundingBox())!
      const x = box.x + box.width / 2
      const y = box.y + box.height / 2
      await cursor(x, y)
      await page.mouse.move(x, y)
      await page.mouse.down()
      await page.mouse.move(x + 2, y + 2)
      await page.mouse.up()
      expect((await snapshot()).dragging).toBe(false)
      expect(await app.evaluate(() => globalThis.mascotE2E.positions)).toHaveLength(0)
      expect(await avatar.evaluate(element => element.getAnimations().length)).toBeGreaterThan(0)
    })
    const drag = async (delay: number) => {
      await app.evaluate((_electron, value) => globalThis.mascotE2E.delayDrag(value), delay)
      const box = (await avatar.boundingBox())!
      const x = box.x + box.width / 2
      const y = box.y + box.height / 2
      await cursor(x, y)
      await page.mouse.move(x, y)
      await page.mouse.down()
      await cursor(x + 12, y)
      await page.mouse.move(x + 12, y)
      if (!delay) await expect.poll(async () => (await snapshot()).dragging).toBe(true)
      await page.mouse.up()
      if (delay) await page.waitForTimeout(delay + 100)
      await expect.poll(async () => (await snapshot()).dragging).toBe(false)
    }
    await test.step('拖动与回执前松手均能正常释放', async () => {
      await drag(200)
      await drag(0)
      expect(await app.evaluate(() => globalThis.mascotE2E.positions.length)).toBeGreaterThan(0)
    })
    await test.step('结果播一次并恢复最新工作状态，气泡保留', async () => {
      await app.evaluate(() => {
        globalThis.mascotE2E.service.setActivity(false, true)
        globalThis.mascotE2E.service.showNotice('任务 A 已完成', 'success', 'A')
      })
      const resultUrl = (await snapshot()).animation!.resultImageUrl!
      await expect.poll(() => image.getAttribute('src')).toBe(resultUrl)
      const firstFrame = await image.getAttribute('style')
      await expect
        .poll(
          async () =>
            (await image.getAttribute('src')) === resultUrl &&
            (await image.getAttribute('style')) !== firstFrame
        )
        .toBe(true)
      await app.evaluate(() => globalThis.mascotE2E.service.setActivity(true, true))
      await expect.poll(async () => (await snapshot()).reaction).toBe(undefined)
      expect((await snapshot()).state).toBe('working')
      await expect
        .poll(() => image.getAttribute('src'))
        .toBe((await snapshot()).animation!.imageUrl)
      await expect(image).toHaveAttribute('style', /translate\([^,]+, -50%\)/)
      await expect(page.getByRole('status')).toHaveText('任务 A 已完成')
    })
    await test.step('失败优先、同任务合并、旧回执隔离及主题切换', async () => {
      await app.evaluate(() =>
        globalThis.mascotE2E.service.showNotice('任务 B 失败', 'failure', 'B')
      )
      const id = (await snapshot()).reactionId!
      await app.evaluate(() => {
        globalThis.mascotE2E.service.showNotice('任务 B 失败', 'failure', 'B')
        globalThis.mascotE2E.service.showNotice('任务 C 已完成', 'success', 'C')
        globalThis.mascotE2E.service.showNotice('任务 C 开始', undefined, 'C')
      })
      expect((await snapshot()).reactionId).toBe(id)
      await page.evaluate(value => window.desktopMascotAPI.reactionEnded(value - 1), id)
      expect((await snapshot()).reaction).toBe('failure')
      await expect(page.getByRole('status')).toHaveText('任务 B 失败')
      for (const theme of ['light', 'dark']) {
        await app.evaluate(
          (_electron, dark) =>
            globalThis.mascotE2E.service.setReady(true, {
              background: dark ? '#1f1f1f' : '#ffffff',
              text: dark ? '#f0f0f0' : '#141414',
              border: dark ? '#434343' : '#d9d9d9',
              radius: 8,
            }),
          theme === 'dark'
        )
        const screenshot = testInfo.outputPath(`mascot-${theme}.png`)
        await page.screenshot({ path: screenshot })
        await testInfo.attach(`${theme} mascot`, { path: screenshot, contentType: 'image/png' })
      }
      await expect(page.getByRole('status')).toHaveText('任务 C 已完成', { timeout: 10000 })
    })
    await test.step('缺少扩展图集、暂停和静态旧包停止反馈', async () => {
      await app.evaluate(() => {
        globalThis.mascotE2E.select('bare')
        globalThis.mascotE2E.service.showNotice('旧包失败', 'failure', 'legacy')
      })
      await expect.poll(async () => (await snapshot()).reaction).toBe(undefined)
      await expect(image).toBeVisible()
      await app.evaluate(() => {
        globalThis.mascotE2E.select('full')
        globalThis.mascotE2E.preferences({ desktopMascotAnimationPaused: true })
        globalThis.mascotE2E.service.showNotice('暂停时失败', 'failure', 'legacy')
      })
      await expect.poll(async () => (await snapshot()).reaction).toBe(undefined)
      await expect
        .poll(() => image.getAttribute('src'))
        .toBe((await snapshot()).animation?.imageUrl)
      const style = await image.getAttribute('style')
      await page.waitForTimeout(100)
      expect(await image.getAttribute('style')).toBe(style)
      await app.evaluate(() => {
        globalThis.mascotE2E.select('static')
        globalThis.mascotE2E.preferences({ desktopMascotAnimationPaused: undefined })
        globalThis.mascotE2E.service.setActivity(false, true)
        globalThis.mascotE2E.service.showNotice('静态包停止', 'stopped', 'static-stop')
      })
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await expect(page.getByRole('status')).toHaveText('静态包停止', { timeout: 10000 })
      await expect(avatar).toHaveClass(/stopped/)
      expect(await avatar.evaluate(element => getComputedStyle(element, '::after').content)).toBe(
        '"?"'
      )
      expect(await avatar.evaluate(element => getComputedStyle(element).animationName)).toBe('none')
      await expect.poll(async () => (await snapshot()).reaction).toBe(undefined)
      await expect(page.getByRole('status')).toHaveText('静态包停止')
      await expect(page.locator('.mascot-static-image')).toBeVisible()
    })
    expect(pageErrors).toEqual([])
    expect(await app.evaluate(() => globalThis.mascotE2E.errors)).toEqual([])
    await app.evaluate(() => globalThis.mascotE2E.dispose())
    await expect.poll(() => app.windows().length).toBe(0)
  } finally {
    await application?.close()
  }
})
