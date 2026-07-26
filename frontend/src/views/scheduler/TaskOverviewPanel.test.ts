import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  if (typeof (globalThis as any).document === 'undefined') {
    ;(globalThis as any).document = {
      createElement: () => ({ innerHTML: '', content: { appendChild: () => {} } }),
      createElementNS: () => ({ innerHTML: '', content: { appendChild: () => {} } }),
      createTextNode: () => ({}),
      createComment: () => ({}),
      documentElement: {},
      head: {},
      body: {},
      querySelector: () => null,
      querySelectorAll: () => [],
    }
  }
  if (typeof (globalThis as any).window === 'undefined') (globalThis as any).window = {}
})

import * as vue from 'vue'
import { defineComponent, h } from 'vue'
import { fileURLToPath } from 'url'
import {
  compileSfcComponent,
  createDom,
  flush,
  installDomStub,
  mountComponent,
  uninstallDomStub,
} from '../scripts/__tests__/mountHelpers'

const testDir = fileURLToPath(new URL('.', import.meta.url))
const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

const TaskTreeStub = defineComponent({
  name: 'TaskTree',
  props: ['taskData'],
  setup(props: any) {
    return () =>
      h(
        'div',
        { class: 'task-tree-stub' },
        (props.taskData ?? []).map((task: any) => task.name).join(',')
      )
  },
})
const TagStub = defineComponent({
  name: 'ATag',
  setup(_props: any, { slots }: any) {
    return () => h('span', { class: 'ant-tag' }, slots.default?.())
  },
})

const mountPanel = () => {
  const component = compileSfcComponent(
    './TaskOverviewPanel.vue',
    {
      vue,
      '@/components/TaskTree.vue': { default: TaskTreeStub },
    },
    testDir
  )
  const components = { TaskTree: TaskTreeStub, ATag: TagStub }
  Object.assign((component as any).components ?? ((component as any).components = {}), components)
  return mountComponent(component, {}, components)
}

describe('TaskOverviewPanel CycleRun preview', () => {
  beforeEach(() => {
    const dom = createDom()
    installDomStub(dom)
    Object.assign(globalThis.window as any, {
      electronAPI: { getLogger: () => logger },
    })
  })

  afterEach(() => {
    uninstallDomStub()
  })

  it('显示当前项、下一项和等待状态，并在任务树未变化时继续更新', async () => {
    const mounted = mountPanel()
    const exposed = mounted.app._instance!.exposed as {
      handleWSMessage: (message: unknown) => void
    }

    exposed.handleWSMessage({
      type: 'Update',
      id: 'task-cycle',
      data: {
        task_info: [{ name: '脚本 A', status: '运行', userList: [] }],
        cycleQueueId: 'queue-a',
        cycleCurrentItemId: 'item-a',
        cycleNextRunAt: '2026-07-25 10:00:00',
        cycleNextList: [
          {
            queueItemId: 'item-a',
            scriptId: 'script-a',
            scriptName: '脚本 A',
            nextRunAt: '2026-07-25 10:00:00',
            isDue: true,
            isRunning: true,
          },
          {
            queueItemId: 'item-b',
            scriptId: 'script-b',
            scriptName: '脚本 B',
            nextRunAt: '2026-07-25 11:00:00',
            isDue: false,
            isRunning: false,
          },
        ],
      },
    })
    await flush()

    expect(mounted.container.textContent).toContain('循环运行')
    expect(mounted.container.textContent).toContain('正在执行 脚本 A')
    expect(mounted.container.textContent).toContain('脚本 B · 2026-07-25 11:00:00')

    exposed.handleWSMessage({
      type: 'Update',
      id: 'task-cycle',
      data: {
        task_info: [{ name: '脚本 A', status: '运行', userList: [] }],
        cycleQueueId: 'queue-a',
        cycleCurrentItemId: null,
        cycleWaitingReason: '等待下一次运行',
        cycleNextRunAt: '2026-07-25 12:00:00',
        cycleNextList: [],
      },
    })
    await flush()

    expect(mounted.container.textContent).toContain('下次运行 2026-07-25 12:00:00')
    expect(mounted.container.textContent).toContain('等待下一次运行')
  })
})
