import { expect, test } from './fixtures'
import type { Locator } from '@playwright/test'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`

test.describe('@queue @scheduler user queue', () => {
  test('builds, reorders, selects accounts, and deletes a queue through the UI', async ({
    app,
    page,
  }) => {
    const post = async (path: string, data: unknown = {}) => {
      const response = await page.request.post(`${backend}${path}`, { data })
      expect(response.ok()).toBeTruthy()
      const body = await response.json()
      expect(body.code).toBe(200)
      return body
    }
    const responseFor = (path: string) =>
      page.waitForResponse(
        response => response.url().endsWith(path) && response.request().method() === 'POST'
      )
    const goTo = async (name: string) => {
      await page
        .getByRole('menuitem')
        .filter({ has: page.getByText(name, { exact: true }) })
        .click()
    }
    const scripts: { scriptId: string; userId?: string; name: string; account: string }[] = []
    let queueId: string | undefined
    const name = 'E2E daily queue'
    const rows = page.locator('.queue-item-card .draggable-row')
    const selectedScripts = rows.locator('.script-select .ant-select-selection-item')

    try {
      for (const suffix of ['A', 'B']) {
        const created = await post('/api/scripts/add', { type: 'MAA' })
        const script = {
          scriptId: created.scriptId as string,
          userId: undefined as string | undefined,
          name: `Queue script ${suffix}`,
          account: `Queue account ${suffix}`,
        }
        scripts.push(script)
        await post('/api/scripts/update', {
          scriptId: script.scriptId,
          data: { Info: { Name: script.name } },
        })
        script.userId = (await post('/api/scripts/user/add', { scriptId: script.scriptId })).userId
        await post('/api/scripts/user/update', {
          scriptId: script.scriptId,
          userId: script.userId,
          data: { Info: { Name: script.account, Status: true, RemainedDay: -1 } },
        })
      }

      await app.goto('/queue')
      const created = responseFor('/api/queue/add')
      await page.getByRole('button', { name: 'New queue' }).click()
      queueId = (await (await created).json()).queueId
      expect(queueId).toBeTruthy()
      await page.locator('.queue-edit-btn').click()
      await page.locator('.queue-title-input').fill(name)
      const renamed = responseFor('/api/queue/update')
      await page.locator('.queue-title-input').press('Enter')
      expect((await (await renamed).json()).code).toBe(200)
      await expect(page.locator('.queue-title-text')).toHaveText(name)

      const startup = page
        .locator('.form-item-vertical')
        .filter({ hasText: 'Run at startup' })
        .locator('.ant-select')
      for (const label of ['Run every time', 'Never']) {
        await startup.click()
        const saved = responseFor('/api/queue/update')
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(label, { exact: true })
          .click()
        expect((await (await saved).json()).code).toBe(200)
        await expect(startup.locator('.ant-select-selection-item')).toHaveText(label)
      }

      for (const [index, script] of scripts.entries()) {
        const added = responseFor('/api/queue/item/add')
        await page.getByRole('button', { name: 'Add task' }).click()
        expect((await (await added).json()).code).toBe(200)
        await expect(rows).toHaveCount(index + 1)
        await rows.nth(index).locator('.script-select').click()
        const saved = responseFor('/api/queue/item/update')
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .filter({ hasText: script.name })
          .click()
        expect((await (await saved).json()).code).toBe(200)
        await expect(selectedScripts.nth(index)).toHaveText(`MAA - ${script.name}`)
      }

      // 七天全选只简化显示；原有星期选择器仍可编辑。
      await post('/api/queue/time/add', { queueId })
      await page.reload()
      await expect(page.locator('.time-set-card .days-select')).toHaveText('Every day')
      await expect(rows.locator('.days-select')).toHaveText(['Every day', 'Every day'])

      await rows.last().scrollIntoViewIfNeeded()
      await expect(rows.first().locator('.drag-handle')).toBeInViewport()
      const reordered = responseFor('/api/queue/item/order')
      const from = await rows.first().locator('.drag-handle').boundingBox()
      const to = await rows.last().boundingBox()
      expect(from).not.toBeNull()
      expect(to).not.toBeNull()
      await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2)
      await page.mouse.down()
      await page.mouse.move(to!.x + 18, to!.y + to!.height - 2, { steps: 12 })
      await page.mouse.up()
      expect((await (await reordered).json()).code).toBe(200)
      await expect(selectedScripts).toHaveText([
        `MAA - ${scripts[1]!.name}`,
        `MAA - ${scripts[0]!.name}`,
      ])

      await goTo('Home')
      await expect(page.locator('.home-title')).toBeVisible()
      await goTo('Queue')
      await expect(selectedScripts).toHaveText([
        `MAA - ${scripts[1]!.name}`,
        `MAA - ${scripts[0]!.name}`,
      ])
      await page.reload()
      await expect(page.locator('.queue-title-text')).toHaveText(name)
      await expect(selectedScripts).toHaveText([
        `MAA - ${scripts[1]!.name}`,
        `MAA - ${scripts[0]!.name}`,
      ])
      await expect(startup.locator('.ant-select-selection-item')).toHaveText('Never')
      await app.evidence('queue-content-reloaded')

      await goTo('Scheduler')
      await page.locator('.task-control .ant-select').first().click()
      await page
        .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: name })
        .click()
      const scopeButton = page.getByRole('button', { name: /Run scope/ })
      await expect(scopeButton).toContainText('2/2')
      await scopeButton.click()
      const scope = page.locator('.ant-popover:visible .queue-scope')
      for (const script of scripts) {
        await expect(scope.getByText(`MAA - ${script.name}`, { exact: true })).toBeVisible()
        await expect(
          scope.getByRole('checkbox', { name: script.account, exact: true })
        ).toBeChecked()
      }
      await scope.getByRole('checkbox', { name: scripts[1]!.account, exact: true }).uncheck()
      await expect(scopeButton).toContainText('1/2')
      await expect(page.locator('.task-control .ant-btn-primary')).toBeEnabled()
      await scope.getByRole('checkbox', { name: scripts[0]!.account, exact: true }).uncheck()
      await expect(scopeButton).toContainText('0/2')
      await expect(page.locator('.task-control .ant-btn-primary')).toBeDisabled()
      await scope.getByRole('checkbox', { name: scripts[1]!.account, exact: true }).check()
      await expect(scopeButton).toContainText('1/2')
      await expect(page.locator('.task-control .ant-btn-primary')).toBeEnabled()
      await scopeButton.click()
      await app.evidence('queue-account-scope')

      await goTo('Queue')
      await rows.first().getByRole('button', { name: 'Delete' }).click()
      await page
        .locator('.ant-popover:visible')
        .getByRole('button', { name: 'Cancel', exact: true })
        .click()
      await expect(selectedScripts).toHaveText([
        `MAA - ${scripts[1]!.name}`,
        `MAA - ${scripts[0]!.name}`,
      ])
      await rows.first().getByRole('button', { name: 'Delete' }).click()
      const removed = responseFor('/api/queue/item/delete')
      await page
        .locator('.ant-popover:visible')
        .getByRole('button', { name: 'OK', exact: true })
        .click()
      expect((await (await removed).json()).code).toBe(200)
      await expect(selectedScripts).toHaveText([`MAA - ${scripts[0]!.name}`])

      await page.getByRole('button', { name: 'Delete this queue' }).click()
      await page
        .locator('.ant-popover:visible')
        .getByRole('button', { name: 'Cancel', exact: true })
        .click()
      await expect(page.locator('.queue-title-text')).toHaveText(name)
      await goTo('Scheduler')
      await page.locator('.task-control .ant-select').first().click()
      await expect(
        page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .filter({ hasText: name })
      ).toBeVisible()
      await page.keyboard.press('Escape')
      await goTo('Queue')
      await page.getByRole('button', { name: 'Delete this queue' }).click()
      const deleted = responseFor('/api/queue/delete')
      await page
        .locator('.ant-popover:visible')
        .getByRole('button', { name: 'OK', exact: true })
        .click()
      expect((await (await deleted).json()).code).toBe(200)
      queueId = undefined
      await expect(page.getByText('No queues', { exact: true })).toBeVisible()
      await goTo('Scheduler')
      await page.locator('.task-control .ant-select').first().click()
      await expect(
        page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .filter({ hasText: name })
      ).toHaveCount(0)
    } finally {
      if (queueId) await post('/api/queue/delete', { queueId })
      for (const script of scripts) {
        if (script.userId)
          await post('/api/scripts/user/delete', {
            scriptId: script.scriptId,
            userId: script.userId,
          })
        await post('/api/scripts/delete', { scriptId: script.scriptId })
      }
    }
  })

  test('edits independent weekday schedules and reloads their saved values', async ({
    app,
    page,
  }) => {
    const post = async (path: string, data: unknown = {}) => {
      const response = await page.request.post(`${backend}${path}`, { data })
      expect(response.ok()).toBeTruthy()
      const body = await response.json()
      expect(body.code).toBe(200)
      return body
    }
    const responseFor = (path: string) =>
      page.waitForResponse(
        response => response.url().endsWith(path) && response.request().method() === 'POST'
      )
    const toggleDays = async (select: Locator, labels: string[], path: string) => {
      await select.click()
      for (const label of labels) {
        const saved = responseFor(path)
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(label, { exact: true })
          .click()
        expect((await (await saved).json()).code).toBe(200)
      }
      await page.keyboard.press('Escape')
      await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0)
    }
    let queueId: string | undefined
    let scriptId: string | undefined
    try {
      scriptId = (await post('/api/scripts/add', { type: 'MAA' })).scriptId
      queueId = (await post('/api/queue/add')).queueId
      const { queueItemId } = await post('/api/queue/item/add', { queueId })
      await post('/api/queue/item/update', {
        queueId,
        queueItemId,
        data: { Info: { ScriptId: scriptId } },
      })

      await app.goto('/queue')
      const timeRows = page.locator('.time-set-card .draggable-row')
      const timeIds: string[] = []
      for (const time of ['08:00', '10:00']) {
        const added = responseFor('/api/queue/time/add')
        await page.getByRole('button', { name: 'Add schedule' }).click()
        timeIds.push((await (await added).json()).timeSetId)
        await expect(timeRows).toHaveCount(timeIds.length)
        // 时刻是测试前置，星期配置在下面通过真实页面控件修改。
        const configTime = await page.evaluate(clock => {
          const [hours, minutes] = clock.split(':').map(Number)
          return new Date(
            Date.UTC(2000, 0, 1, hours, minutes) + new Date().getTimezoneOffset() * 60_000
          ).toISOString()
        }, time)
        await post('/api/queue/time/update', {
          queueId,
          timeSetId: timeIds.at(-1),
          data: { Info: { Time: configTime } },
        })
      }
      await page.reload()
      const timeDays = timeRows.locator('.days-select')
      const taskDays = page.locator('.queue-item-card .days-select')
      await expect(timeDays).toHaveText(['Every day', 'Every day'])
      await expect(taskDays).toHaveText('Every day')
      await toggleDays(timeDays.first(), ['Sat', 'Sun'], '/api/queue/time/update')
      await toggleDays(
        timeDays.last(),
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
        '/api/queue/time/update'
      )
      await expect(timeDays.first().locator('.ant-select-selection-item')).toHaveText([
        'Mon',
        'Tue',
        'Wed',
        'Thu',
        'Fri',
      ])
      await expect(timeDays.last().locator('.ant-select-selection-item')).toHaveText(['Sat', 'Sun'])

      // 清空与重新全选都沿原接口保存，两个定时项互不覆盖。
      await toggleDays(
        timeDays.first(),
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
        '/api/queue/time/update'
      )
      await expect(timeDays.first().locator('.ant-select-selection-placeholder')).toHaveText(
        'Select the days'
      )
      const emptyTimes = await post('/api/queue/time/get', { queueId })
      expect(emptyTimes.data[timeIds[0]!].Info.Days).toEqual([])
      await toggleDays(
        timeDays.first(),
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        '/api/queue/time/update'
      )
      await expect(timeDays.first().locator('.ant-select-selection-item-content')).toHaveText(
        'Every day'
      )
      const fullTimes = await post('/api/queue/time/get', { queueId })
      expect(fullTimes.data[timeIds[0]!].Info.Days).toEqual([
        'Monday',
        'Tuesday',
        'Wednesday',
        'Thursday',
        'Friday',
        'Saturday',
        'Sunday',
      ])
      await toggleDays(timeDays.first(), ['Sat', 'Sun'], '/api/queue/time/update')
      const originalTimes = await post('/api/queue/time/get', { queueId })

      await toggleDays(taskDays, ['Tue', 'Thu', 'Sat', 'Sun'], '/api/queue/item/update')
      await toggleDays(taskDays, ['Mon', 'Wed', 'Fri'], '/api/queue/item/update')
      await expect(taskDays.locator('.ant-select-selection-placeholder')).toHaveText(
        'Select the days'
      )
      const emptyTasks = await post('/api/queue/item/get', { queueId })
      expect(emptyTasks.data[queueItemId].Schedule.Days).toEqual([])
      await toggleDays(taskDays, ['Mon', 'Wed', 'Fri'], '/api/queue/item/update')

      await page.reload()
      await expect(timeRows.first().locator('.ant-picker input')).toHaveValue('08:00')
      await expect(timeRows.last().locator('.ant-picker input')).toHaveValue('10:00')
      await expect(timeDays.first().locator('.ant-select-selection-item')).toHaveText([
        'Mon',
        'Tue',
        'Wed',
        'Thu',
        'Fri',
      ])
      await expect(timeDays.last().locator('.ant-select-selection-item')).toHaveText(['Sat', 'Sun'])
      await expect(taskDays.locator('.ant-select-selection-item')).toHaveText(['Mon', 'Wed', 'Fri'])
      const savedTimes = await post('/api/queue/time/get', { queueId })
      expect(savedTimes.data).toEqual(originalTimes.data)
      expect(savedTimes.data[timeIds[0]!].Info.Days).toEqual([
        'Monday',
        'Tuesday',
        'Wednesday',
        'Thursday',
        'Friday',
      ])
      expect(savedTimes.data[timeIds[1]!].Info.Days).toEqual(['Saturday', 'Sunday'])
      const savedTasks = await post('/api/queue/item/get', { queueId })
      expect(savedTasks.data[queueItemId].Schedule.Days).toEqual(['Monday', 'Wednesday', 'Friday'])
      await page.locator('.time-set-card').scrollIntoViewIfNeeded()
      await app.evidence('queue-weekday-editing-reloaded')
    } finally {
      if (queueId) await post('/api/queue/delete', { queueId })
      if (scriptId) await post('/api/scripts/delete', { scriptId })
    }
  })
})
