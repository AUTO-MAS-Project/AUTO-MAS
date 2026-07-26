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
} from './scripts/__tests__/mountHelpers'

/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

const testDir = fileURLToPath(new URL('.', import.meta.url))

const IconStub = defineComponent({
  setup() {
    return () => h('span', { class: 'icon-stub' })
  },
})

const ButtonStub = defineComponent({
  props: ['disabled', 'loading', 'type', 'size'],
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

const SegmentedStub = defineComponent({
  props: ['value', 'options'],
  emits: ['change'],
  setup(props: any, { emit }: any) {
    return () =>
      h(
        'div',
        { class: 'ant-segmented', 'data-value': props.value },
        (props.options ?? []).map((option: any) =>
          h(
            'button',
            {
              class: `segment-${option.value}`,
              onClick: () => emit('change', option.value),
            },
            option.label
          )
        )
      )
  },
})

const SlotStub = defineComponent({
  setup(_props, { slots }) {
    return () => h('div', slots.default?.())
  },
})

const InputStub = defineComponent({
  props: ['value'],
  emits: ['update:value'],
  setup() {
    return () => h('input')
  },
})

describe('LogToolbar interactions', () => {
  beforeEach(() => installDomStub(createDom()))
  afterEach(() => uninstallDomStub())

  const mountToolbar = (props: Record<string, unknown> = {}) => {
    const component = compileSfcComponent(
      './Logs/components/LogToolbar.vue',
      {
        vue,
        '@ant-design/icons-vue': {
          CopyOutlined: IconStub,
          DeleteOutlined: IconStub,
          DownloadOutlined: IconStub,
          PauseCircleOutlined: IconStub,
          PlayCircleOutlined: IconStub,
          ReloadOutlined: IconStub,
          SyncOutlined: IconStub,
        },
      },
      testDir
    )
    ;(component as any).components = {
      AButton: ButtonStub,
      ASegmented: SegmentedStub,
      ASpace: SlotStub,
      ATooltip: SlotStub,
      ASelect: InputStub,
      AInputSearch: InputStub,
      'a-button': ButtonStub,
      'a-segmented': SegmentedStub,
      'a-space': SlotStub,
      'a-tooltip': SlotStub,
      'a-select': InputStub,
      'a-input-search': InputStub,
    }
    return mountComponent(component, {
      source: 'app',
      level: '',
      keyword: '',
      isRealtime: true,
      isPaused: false,
      exporting: false,
      refreshing: false,
      canCopy: true,
      canClear: true,
      ...props,
    })
  }

  it('switches the selected log source', async () => {
    const sources: string[] = []
    const { container } = mountToolbar({
      'onUpdate:source': (value: string) => sources.push(value),
    })
    await flush()

    findByClass(container, 'segment-frontend').dispatchEvent('click')
    await flush()

    expect(sources).toEqual(['frontend'])
  })

  it('emits refresh, copy, clear and export actions', async () => {
    const events: string[] = []
    const { container } = mountToolbar({
      onRefresh: () => events.push('refresh'),
      onCopy: () => events.push('copy'),
      onClear: () => events.push('clear'),
      onExport: () => events.push('export'),
    })
    await flush()

    const buttons = findAllByClass(container, 'ant-btn')
    for (const [label, event] of [
      ['刷新', 'refresh'],
      ['复制', 'copy'],
      ['清空视图', 'clear'],
      ['导出', 'export'],
    ]) {
      buttons.find(button => button.textContent.includes(label))?.dispatchEvent('click')
      await flush()
      expect(events).toContain(event)
    }
  })
})
