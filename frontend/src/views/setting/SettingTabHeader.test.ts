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
})

import * as vue from 'vue'
import { defineComponent, h } from 'vue'
import { fileURLToPath } from 'node:url'
import {
  compileSfcComponent,
  createDom,
  findAllByClass,
  findByClass,
  flush,
  installDomStub,
  mountComponent,
  uninstallDomStub,
} from '../scripts/__tests__/mountHelpers'

/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

const testDir = fileURLToPath(new URL('.', import.meta.url))

const UndoIconStub = defineComponent({
  setup() {
    return () => h('span', { class: 'undo-icon' })
  },
})

const ButtonStub = defineComponent({
  props: ['type', 'disabled', 'loading', 'danger', 'size'],
  emits: ['click'],
  setup(props: any, { emit, slots }: any) {
    return () =>
      h(
        'button',
        {
          class: 'ant-btn',
          disabled: props.disabled,
          onClick: () => emit('click'),
        },
        slots.default?.()
      )
  },
})

const AlertStub = defineComponent({
  props: ['type', 'message', 'closable', 'showIcon'],
  emits: ['close'],
  setup(props: any, { emit, slots }: any) {
    return () =>
      h(
        'div',
        {
          class: `ant-alert ant-alert-${props.type}`,
          onClick: () => emit('close'),
        },
        [h('span', { class: 'alert-message' }, props.message), slots.action?.()]
      )
  },
})

describe('SettingTabHeader interactions', () => {
  beforeEach(() => installDomStub(createDom()))
  afterEach(() => uninstallDomStub())

  const mountHeader = (props: Record<string, unknown> = {}) => {
    const component = compileSfcComponent(
      './SettingTabHeader.vue',
      {
        vue,
        '@ant-design/icons-vue': { UndoOutlined: UndoIconStub },
      },
      testDir
    )
    ;(component as any).components = {
      AButton: ButtonStub,
      AAlert: AlertStub,
      'a-button': ButtonStub,
      'a-alert': AlertStub,
    }
    return mountComponent(component, props)
  }

  it('emits restore and retry actions without rendering another title', async () => {
    const events: string[] = []
    const { container } = mountHeader({
      description: '设置说明',
      hasPending: true,
      pendingCount: 2,
      canRestoreDefaults: true,
      onRestoreDefaults: () => events.push('restore'),
      onRetryPending: () => events.push('retry'),
    })
    await flush()

    expect(container.textContent).toContain('设置说明')
    expect(container.textContent).not.toContain('界面设置')

    const buttons = findAllByClass(container, 'ant-btn')
    buttons.find(button => button.textContent.includes('恢复默认'))?.dispatchEvent('click')
    buttons.find(button => button.textContent.includes('重试保存'))?.dispatchEvent('click')
    await flush()

    expect(events).toEqual(['restore', 'retry'])
  })

  it('emits clearError from the inline error alert', async () => {
    const clearError = vi.fn()
    const { container } = mountHeader({
      error: '保存失败',
      onClearError: clearError,
    })
    await flush()

    expect(container.textContent).toContain('保存失败')
    findByClass(container, 'ant-alert-error').dispatchEvent('click')
    await flush()

    expect(clearError).toHaveBeenCalledOnce()
  })
})
