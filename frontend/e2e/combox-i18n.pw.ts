import { expect, test } from './fixtures'

/**
 * @i18n-dropdown 下拉框选项文案的语言回归。
 *
 * 背景：后端 combox 接口（任务/脚本/模拟器下拉）原先直接返回中文文案
 * （「未选择」「队列 - xxx」「脚本 - xxx」），英文/日文界面打开下拉会看到中文。
 * 这里锁定「英文界面下拉框选项不含汉字」这条用户可见的契约。
 */
const CJK = /[\u3400-\u4dbf\u4e00-\u9fff]/

const backendBaseUrl = () => `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`

const openSelectAndReadOptions = async (
  page: import('@playwright/test').Page,
  selector: string
): Promise<string[]> => {
  const select = page.locator(selector).first()
  await expect(select).toBeVisible()
  await select.click()
  const options = page.locator('.ant-select-dropdown:visible .ant-select-item-option-content')
  await expect(options.first()).toBeVisible()
  const texts = await options.allInnerTexts()
  await page.keyboard.press('Escape')
  return texts
}

test.describe('下拉框选项语言', { tag: '@i18n' }, () => {
  test('英文界面下，队列脚本下拉与调度台任务下拉的选项没有中文', async ({ app, page }) => {
    // 造一条脚本与一个队列。默认名是后端造的中文数据（「新 MAA 脚本」「新队列」），
    // 实体名属于用户数据不算界面泄漏，先改成 ASCII 名，剩下的中文才是界面文案问题。
    // scripts/add / queue/add 的 id 在响应顶层而不是 data 字段里，走 raw 读完整响应。
    const addScriptResponse = await app.api.raw.post(`${backendBaseUrl()}/api/scripts/add`, {
      data: { type: 'MAA', scriptId: null },
    })
    expect(addScriptResponse.ok()).toBeTruthy()
    const script = (await addScriptResponse.json()) as { scriptId: string; code: number }
    expect(script.code).toBe(200)
    expect(script.scriptId).toBeTruthy()
    await app.api.post('/api/scripts/update', {
      scriptId: script.scriptId,
      data: { Info: { Name: 'E2E Dropdown Script' } },
    })
    const addQueueResponse = await app.api.raw.post(`${backendBaseUrl()}/api/queue/add`, {
      data: {},
    })
    expect(addQueueResponse.ok()).toBeTruthy()
    const queue = (await addQueueResponse.json()) as { queueId: string; code: number }
    expect(queue.code).toBe(200)
    expect(queue.queueId).toBeTruthy()
    await app.api.post('/api/queue/update', {
      queueId: queue.queueId,
      data: { Info: { Name: 'E2E Dropdown Queue' } },
    })

    try {
      // 队列页「添加任务」后的脚本下拉
      await app.goto('/queue')
      await page.getByRole('button', { name: 'Add task' }).click()
      const scriptOptions = await openSelectAndReadOptions(page, '.script-select')
      expect(scriptOptions.length).toBeGreaterThan(0)
      const scriptLeaks = scriptOptions.filter(text => CJK.test(text))
      expect(
        scriptLeaks,
        `脚本下拉在英文界面下出现了中文选项：${JSON.stringify(scriptLeaks)}`
      ).toEqual([])

      // 调度台的任务下拉
      await app.goto('/scheduler')
      const taskOptions = await openSelectAndReadOptions(page, '.task-control .ant-select')
      expect(taskOptions.length).toBeGreaterThan(0)
      const taskLeaks = taskOptions.filter(text => CJK.test(text))
      expect(taskLeaks, `任务下拉在英文界面下出现了中文选项：${JSON.stringify(taskLeaks)}`).toEqual(
        []
      )

      await app.evidence('combox-dropdown-no-cjk')
    } finally {
      // 整套用例共享同一个数据根：造出来的脚本/队列必须删掉，
      // 否则后面断言「空状态」的用例（config-flows / queue）会看到残留数据而失败。
      // 清理不许吞异常：吞掉之后症状会出现在别的文件里，排查全靠猜。
      await app.api.post('/api/queue/delete', { queueId: queue.queueId })
      await app.api.post('/api/scripts/delete', { scriptId: script.scriptId })
    }
  })
})
