import { expect, test } from './fixtures'

const backendBaseUrl = () => `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`

type QueueIndexEntry = { uid: string; type: string }

type App = { api: { raw: import('@playwright/test').APIRequestContext } }

/** 电源操作下拉里 9 个信号对应的英文文案，顺序与 schedulerConstants.ts 的 POWER_ACTION_LABEL_KEY 一致。 */
const POWER_LABELS = [
  'Do nothing',
  'Shut down',
  'Force shut down',
  'Restart',
  'Hibernate',
  'Sleep',
  'Quit AUTO-MAS',
  'Restart AUTO-MAS',
  'Sign out',
]

/** 直接问后端要队列列表：页面上看不出这条数据是谁造的。 */
const readQueueIndex = async (app: App): Promise<QueueIndexEntry[]> => {
  const response = await app.api.raw.post(`${backendBaseUrl()}/api/queue/get`, { data: {} })
  const body = (await response.json()) as { code: number; index: QueueIndexEntry[] }
  expect(body.code, '查询队列列表失败').toBe(200)
  return body.index
}

test.describe('@scheduler safeguards', () => {
  test('keeps an empty dispatch safe and manages idle run panels', async ({ app, page }) => {
    const taskOptionsResponse = page.waitForResponse(
      response =>
        response.url().includes('/api/info/combox/task') && response.request().method() === 'POST'
    )

    await app.goto('/scheduler')

    const response = await taskOptionsResponse
    expect(response.ok()).toBeTruthy()
    const payload = await response.json()
    expect(payload.code).toBe(200)
    // labelKey/kind 是 combox i18n 契约：前端靠 kind 区分队列/脚本任务、靠 labelKey 翻译占位文案
    expect(payload.data?.[0]).toMatchObject({
      label: '未选择',
      value: null,
      labelKey: 'common.notSelected',
      kind: 'placeholder',
    })

    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()
    const runButtons = page.locator('.task-control .ant-btn')
    await expect(runButtons).toHaveCount(1)
    await expect(runButtons.first()).toBeDisabled()
    await expect(page.locator('.overview-panel .empty-image')).toBeVisible()
    await expect(page.locator('.log-panel .empty-image')).toBeVisible()

    await page.locator('.tab-add-btn').click()
    await expect(page.locator('.ant-tabs-tab')).toHaveCount(2)
    await expect(page.locator('.task-control .ant-btn')).toHaveCount(2)
    await expect(page.locator('.task-control .ant-btn').last()).toBeDisabled()
    await expect(page.locator('.tab-remove-btn')).toBeEnabled()

    await page.locator('.tab-remove-btn').click()
    await expect(page.getByText('Close idle consoles', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Close it', exact: true }).click()
    await expect(page.getByText('Close idle consoles', { exact: true })).toBeHidden()
    await expect(page.locator('.ant-tabs-tab')).toHaveCount(1)

    await app.evidence('scheduler-empty-protection')
  })

  // 电源操作决定任务跑完之后机器会怎样：少一项译文、少一个选项，用户就没法设置自己想要的收尾动作。
  test('power action select shows every signal in the interface language', async ({
    app,
    page,
  }) => {
    await app.goto('/scheduler')

    const powerSelect = page.locator('.power-select')
    await expect(powerSelect).toContainText('Do nothing')

    await powerSelect.click()
    const options = page.locator('.ant-select-dropdown:visible .ant-select-item-option-content')
    await expect(options).toHaveCount(POWER_LABELS.length)
    const texts = (await options.allInnerTexts()).map(text => text.trim())
    // 顺序也断言：信号是后端枚举，乱序会让「跑完关机」这类固定操作在列表里跳位置
    expect(texts, '电源操作下拉的选项文案或顺序和 schedulerConstants.ts 对不上').toEqual(
      POWER_LABELS
    )

    // Esc 是键盘用户唯一的收起方式；这里断的是「下拉本身没了」，不是某个选项
    await page.keyboard.press('Escape')
    await expect(page.locator('.ant-select-dropdown:visible'), '按 Esc 应该能收起下拉').toHaveCount(
      0
    )
    await app.evidence('scheduler-power-select')
  })

  // 真实用户的核心链路：建好队列 → 在调度台选中它 → 确认可以启动，并能看到这次会跑哪些账号。
  test('selecting a queue enables Run and explains the run scope', async ({ app, page }) => {
    expect(
      (await readQueueIndex(app)).map(entry => entry.uid),
      '队列页不是空状态：有别的用例留下了队列数据（造数据的用例必须在 finally 里删掉）'
    ).toEqual([])

    try {
      await app.goto('/queue')
      await page.getByRole('button', { name: 'New queue' }).click()
      const queueTitle = page.locator('.queue-title-text')
      await expect(queueTitle).toBeVisible()
      await page.locator('.queue-edit-btn').click()
      const nameInput = page.locator('.queue-title-input')
      await nameInput.fill('E2E scheduler queue')
      const renameResponse = page.waitForResponse(
        response =>
          response.url().endsWith('/api/queue/update') &&
          response.request().method() === 'POST' &&
          response.ok()
      )
      await nameInput.press('Enter')
      await renameResponse
      await expect(queueTitle).toHaveText('E2E scheduler queue')

      // 换页会重新拉 /api/info/combox/task，新队列才会出现在下拉里
      await app.goto('/scheduler')
      const taskSelect = page.locator('.task-control .ant-select').first()
      await taskSelect.click()
      const queueOption = page
        .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: 'E2E scheduler queue' })
      await expect(queueOption, '调度台的任务下拉里找不到刚建的队列').toHaveCount(1)
      await queueOption.click()

      // 选中队列后启动按钮才能点；队列里一个账号都没有时放开按钮，交给脚本自己报无用户
      const runButton = page.locator('.task-control .ant-btn').last()
      await expect(runButton).toBeEnabled()

      // 运行范围面板：空队列要明确说「没有能跑的账号」，而不是给一个空白浮层
      const scopeButton = page.locator('.task-control').getByRole('button', { name: /Run scope/ })
      await expect(scopeButton).toBeVisible()
      await expect(scopeButton).toContainText('0/0')
      await scopeButton.click()
      await expect(page.locator('.queue-scope')).toBeVisible()
      await expect(page.locator('.queue-scope')).toContainText('No account can run')
      await app.evidence('scheduler-queue-selected')
      await page.keyboard.press('Escape')

      // 自动代理模式下还要能挑选从哪个脚本续跑（默认第一个），这一项在循环队列下才该消失
      await expect(page.locator('.task-control .ant-select').nth(1)).toBeVisible()
    } finally {
      for (const entry of await readQueueIndex(app)) {
        await app.api.post('/api/queue/delete', { queueId: entry.uid })
      }
      expect(await readQueueIndex(app), '清理失败：队列数据还在，后面的用例会看到残留').toEqual([])
    }
  })
})
