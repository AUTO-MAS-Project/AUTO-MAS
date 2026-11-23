import {
  createRenderer,
  defineComponent,
  h,
  nextTick,
  ref,
  ssrContextKey,
  type Component,
} from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

interface MockConfirmCall {
  config: Record<string, unknown>
}

const confirmCalls: MockConfirmCall[] = []

vi.mock('ant-design-vue', () => {
  const ModalContextHolder = defineComponent({
    name: 'ModalContextHolder',
    setup: () => () => null,
  })
  const confirm = vi.fn((config: Record<string, unknown>) => {
    confirmCalls.push({ config })
    return { update: vi.fn(), destroy: vi.fn() }
  })
  return {
    Modal: {
      confirm,
      useModal: () => [{ confirm }, ModalContextHolder],
    },
  }
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import AppModal from './AppModal.vue'

interface StubNode {
  tag: string
  children: StubNode[]
}

const noopRenderer = createRenderer<StubNode, StubNode>({
  patchProp() {},
  insert(el, parent) {
    parent.children.push(el)
  },
  remove(el) {
    void el
  },
  createElement(tag) {
    return { tag, children: [] }
  },
  createText() {
    return { tag: '#text', children: [] }
  },
  createComment() {
    return { tag: '#comment', children: [] }
  },
  setText() {},
  setElementText() {},
  parentNode() {
    return null
  },
  nextSibling() {
    return null
  },
})

// Vite 在 Node 单测环境下仅生成 ssrRender；补一个空客户端 render 以驱动真实父子 prop 响应式更新。
const ClientAppModal: Component = { ...AppModal, render: () => null }

function mountParent(options?: {
  initialOpen?: boolean
  initialDirty?: boolean
  initialSubmitting?: boolean
  initialSessionKey?: string
}) {
  const open = ref(options?.initialOpen ?? true)
  const dirty = ref(options?.initialDirty ?? true)
  const submitting = ref(options?.initialSubmitting ?? false)
  const sessionKey = ref(options?.initialSessionKey ?? 'item-1')
  const onParentCancel = vi.fn()
  const modalRef = ref<{ requestClose: () => Promise<boolean> } | null>(null)

  const Parent = defineComponent({
    setup() {
      return () =>
        h(ClientAppModal, {
          ref: modalRef,
          open: open.value,
          'onUpdate:open': (value: boolean) => {
            open.value = value
          },
          dirty: dirty.value,
          submitting: submitting.value,
          sessionKey: sessionKey.value,
          title: '编辑配置',
          onCancel: onParentCancel,
        })
    },
  })

  const app = noopRenderer.createApp(Parent)
  app.provide(ssrContextKey, { modules: new Set() })

  const container: StubNode = { tag: 'root', children: [] }
  app.mount(container)

  return {
    open,
    dirty,
    submitting,
    sessionKey,
    onParentCancel,
    requestClose: () => {
      if (!modalRef.value) throw new Error('AppModal ref not mounted')
      return modalRef.value.requestClose()
    },
    unmount: () => app.unmount(),
  }
}

describe('AppModal 父子绑定关闭保护', () => {
  beforeEach(() => {
    confirmCalls.length = 0
  })

  it('父组件在同一更新轮次先关再开并切换 sessionKey 时，旧确认不能关闭新编辑', async () => {
    const ctx = mountParent({ initialSessionKey: 'doc-1' })

    // 对 doc-1 触发关闭，弹出第一份待决确认
    const firstClose = ctx.requestClose()
    expect(confirmCalls).toHaveLength(1)
    const firstOnOk = confirmCalls[0]!.config.onOk as () => Promise<void>

    // 父组件在同一 tick 内先关再开并切到 doc-2：Vue 合并 open 更新后子组件仍看到 open=true，靠 sessionKey 区分会话
    ctx.open.value = false
    ctx.open.value = true
    ctx.sessionKey.value = 'doc-2'
    await nextTick()

    // 旧确认点「确定」后，不应关掉已经切到 doc-2 的新窗口
    await firstOnOk()
    await expect(firstClose).resolves.toBe(false)
    await nextTick()
    expect(ctx.open.value).toBe(true)
    expect(ctx.onParentCancel).not.toHaveBeenCalled()

    // doc-2 自己触发关闭可正常弹新确认并关闭
    const secondClose = ctx.requestClose()
    expect(confirmCalls).toHaveLength(2)
    await (confirmCalls[1]!.config.onOk as () => Promise<void>)()
    await expect(secondClose).resolves.toBe(true)
    await nextTick()
    expect(ctx.open.value).toBe(false)
    expect(ctx.onParentCancel).toHaveBeenCalledTimes(1)

    ctx.unmount()
  })

  it('等确认期间父组件开始提交时，旧确认不会关闭正在保存的弹窗', async () => {
    const ctx = mountParent({ initialSessionKey: 'doc-1' })

    const pendingClose = ctx.requestClose()
    expect(confirmCalls).toHaveLength(1)
    const firstOnOk = confirmCalls[0]!.config.onOk as () => Promise<void>

    ctx.submitting.value = true
    await nextTick()

    await firstOnOk()
    await expect(pendingClose).resolves.toBe(false)
    await nextTick()
    expect(ctx.open.value).toBe(true)
    expect(ctx.onParentCancel).not.toHaveBeenCalled()

    ctx.unmount()
  })
})
