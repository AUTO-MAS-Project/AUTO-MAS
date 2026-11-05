import { expect, test } from './fixtures'

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

      await page.keyboard.press('Escape')
      await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0)
      const timeAdded = responseFor('/api/queue/time/add')
      await page.getByRole('button', { name: 'Add schedule' }).click()
      expect((await (await timeAdded).json()).code).toBe(200)
      const timeDays = page.locator('.time-set-card .draggable-row .days-cell')
      await expect(timeDays).toHaveText(['Every day'])
      await expect(timeDays.locator('input, button, .ant-select')).toHaveCount(0)

      const weekdays = rows.locator('.days-select')
      await expect(weekdays).toHaveText(['Every day', 'Every day'])
      await weekdays.first().click()
      for (const day of ['Tue', 'Thu', 'Sat', 'Sun']) {
        const saved = responseFor('/api/queue/item/update')
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(day, { exact: true })
          .click()
        expect((await (await saved).json()).code).toBe(200)
      }
      await page.keyboard.press('Escape')
      await expect(weekdays.first().locator('.ant-select-selection-item')).toHaveText([
        'Mon',
        'Wed',
        'Fri',
      ])

      // 空选择按原规则保存为空，不把它折叠成每天。
      await weekdays.first().click()
      for (const day of ['Mon', 'Wed', 'Fri']) {
        const saved = responseFor('/api/queue/item/update')
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(day, { exact: true })
          .click()
        expect((await (await saved).json()).code).toBe(200)
      }
      await page.keyboard.press('Escape')
      await expect(weekdays.first().locator('.ant-select-selection-placeholder')).toHaveText(
        'Select the days'
      )
      await weekdays.first().click()
      for (const day of ['Mon', 'Wed', 'Fri']) {
        const saved = responseFor('/api/queue/item/update')
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(day, { exact: true })
          .click()
        expect((await (await saved).json()).code).toBe(200)
      }
      await page.keyboard.press('Escape')

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
      await expect(weekdays.first()).toHaveText('Every day')
      await expect(weekdays.last().locator('.ant-select-selection-item')).toHaveText([
        'Mon',
        'Wed',
        'Fri',
      ])
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

  test('preserves raw trigger weekdays while task weekdays are edited and reloaded', async ({
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
    let queueId: string | undefined
    let scriptId: string | undefined
    try {
      scriptId = (await post('/api/scripts/add', { type: 'MAA' })).scriptId
      queueId = (await post('/api/queue/add')).queueId
      const taskIds: string[] = []
      const allDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
      for (const schedule of [
        { Enabled: false, Days: allDays },
        { Enabled: true, Days: [] },
      ]) {
        const { queueItemId } = await post('/api/queue/item/add', { queueId })
        taskIds.push(queueItemId)
        await post('/api/queue/item/update', {
          queueId,
          queueItemId,
          data: { Info: { ScriptId: scriptId }, Schedule: schedule },
        })
      }

      for (const info of [
        { Enabled: false, Days: ['Tuesday', 'Thursday'] },
        { Enabled: true, Days: [] },
      ]) {
        const { timeSetId } = await post('/api/queue/time/add', { queueId })
        await post('/api/queue/time/update', { queueId, timeSetId, data: { Info: info } })
      }
      const originalTimes = await post('/api/queue/time/get', { queueId })
      const originalTasks = await post('/api/queue/item/get', { queueId })

      await app.goto('/queue')
      const timeRows = page.locator('.time-set-card .draggable-row')
      const timeDays = timeRows.locator('.days-cell')
      const taskDays = page.locator('.queue-item-card .draggable-row .days-select')
      await expect(timeDays).toHaveText(['Tue, Thu', '—'])
      await expect(timeDays.locator('input, button, .ant-select')).toHaveCount(0)
      await expect(taskDays.first()).toHaveText('Every day')
      await expect(taskDays.last().locator('.ant-select-selection-placeholder')).toHaveText(
        'Select the days'
      )

      await taskDays.first().click()
      for (const day of ['Tue', 'Thu', 'Sat', 'Sun']) {
        const saved = responseFor('/api/queue/item/update')
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(day, { exact: true })
          .click()
        const response = await saved
        expect((await response.json()).code).toBe(200)
        expect(response.request().postDataJSON()).toMatchObject({
          queueId,
          queueItemId: taskIds[0],
        })
      }
      await page.keyboard.press('Escape')
      await expect(taskDays.first().locator('.ant-select-selection-item')).toHaveText([
        'Mon',
        'Wed',
        'Fri',
      ])
      // 此时任务日期与定时触发日期完全错开，上方仍展示原始日期。
      await expect(timeDays).toHaveText(['Tue, Thu', '—'])

      for (const label of ['Enabled', 'Disabled']) {
        await timeRows.first().locator('.status-select').click()
        const saved = responseFor('/api/queue/time/update')
        await page
          .locator('.ant-select-dropdown:visible .ant-select-item-option-content')
          .getByText(label, { exact: true })
          .click()
        expect((await (await saved).json()).code).toBe(200)
        await expect(
          timeRows.first().locator('.status-select .ant-select-selection-item')
        ).toHaveText(label)
        await expect(timeDays).toHaveText(['Tue, Thu', '—'])
      }

      await page.reload()
      await expect(timeDays).toHaveText(['Tue, Thu', '—'])
      await expect(timeDays.locator('input, button, .ant-select')).toHaveCount(0)
      await expect(taskDays.first().locator('.ant-select-selection-item')).toHaveText([
        'Mon',
        'Wed',
        'Fri',
      ])
      await expect(taskDays.last().locator('.ant-select-selection-placeholder')).toHaveText(
        'Select the days'
      )
      const savedTimes = await post('/api/queue/time/get', { queueId })
      expect(savedTimes.index).toEqual(originalTimes.index)
      expect(savedTimes.data).toEqual(originalTimes.data)
      const savedTasks = await post('/api/queue/item/get', { queueId })
      expect(savedTasks.index).toEqual(originalTasks.index)
      expect(savedTasks.data).toEqual({
        ...originalTasks.data,
        [taskIds[0]!]: {
          ...originalTasks.data[taskIds[0]!],
          Schedule: {
            ...originalTasks.data[taskIds[0]!].Schedule,
            Days: ['Monday', 'Wednesday', 'Friday'],
          },
        },
      })
      await page.locator('.time-set-card').scrollIntoViewIfNeeded()
      await app.evidence('queue-trigger-and-task-weekdays')
    } finally {
      if (queueId) await post('/api/queue/delete', { queueId })
      if (scriptId) await post('/api/scripts/delete', { scriptId })
    }
  })
})
