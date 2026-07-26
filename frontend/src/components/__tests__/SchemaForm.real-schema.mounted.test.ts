import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  if (typeof (globalThis as { document?: unknown }).document === 'undefined') {
    ;(globalThis as { document: unknown }).document = {
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
  if (typeof (globalThis as { window?: unknown }).window === 'undefined') {
    ;(globalThis as { window: unknown }).window = {}
  }
})

import * as vue from 'vue'
import { defineComponent, h, type App } from 'vue'
import { fileURLToPath } from 'url'
import {
  compileSfcComponent,
  createDom,
  findAllByClass,
  installDomStub,
  mountComponent,
  uninstallDomStub,
  type FakeElement,
} from '@/views/scripts/__tests__/mountHelpers'
import { useSchemaFormModel } from '@/composables/useSchemaFormModel'
import * as sensitiveStrategy from '@/composables/useSensitiveFieldStrategy'
import * as schemaFormCore from '@/utils/schemaFormCore'
import type { SchemaDefinition, SchemaFieldDefinition } from '@/types/schemaForm'

/**
 * Lane 15：SchemaForm + MaaEnd/HSR 真实 schema mounted 测试
 *
 * 目标：验证 SchemaForm.vue 在真实 HSR / MaaEnd 用户 schema 下能正确挂载，
 * 且敏感字段（password / token / ServerChanKey）的明文不会进入 DOM 初值。
 *
 * 真实 schema 来源（与 sensitive-fields.test.ts 一致）：
 * - HSR 用户：build/w/b2/automas_script_hsr/source/src/automas_script_hsr/schema.py
 *   - HSRUserSRAConfig.Id / Password（format='password', sensitive=True）
 *   - HSRUserNotifyConfig.ServerChanKey（sensitive=True）
 * - MaaEnd 用户：app/models/config.py MaaEndUserConfig
 *   - Info.Password / Info.SklandToken（EncryptValidator）
 *   - Notify.ServerChanKey（EncryptValidator）
 */

const field = (overrides: Partial<SchemaFieldDefinition> = {}): SchemaFieldDefinition => ({
  type: 'string',
  ...overrides,
})

const hsrUserSchema: SchemaDefinition = {
  groups: [
    {
      key: 'SRA',
      label: 'SRA 账号',
      fields: [
        field({
          key: 'SRA.Id',
          type: 'string',
          format: 'password',
          sensitive: true,
          label: '账号',
        }),
        field({
          key: 'SRA.Password',
          type: 'string',
          format: 'password',
          sensitive: true,
          label: '密码',
        }),
      ],
    },
    {
      key: 'Notify',
      label: '通知',
      fields: [
        field({
          key: 'Notify.ServerChanKey',
          type: 'string',
          sensitive: true,
          label: 'ServerChan Key',
        }),
      ],
    },
  ],
}

const maaEndUserSchema: SchemaDefinition = {
  groups: [
    {
      key: 'Info',
      label: '基础信息',
      fields: [
        field({ key: 'Info.Name', type: 'string', label: '用户名' }),
        field({
          key: 'Info.Password',
          type: 'string',
          format: 'password',
          sensitive: true,
          label: '密码',
        }),
        field({
          key: 'Info.SklandToken',
          type: 'string',
          sensitive: true,
          label: '鹰角网络通行证登录凭证',
        }),
      ],
    },
    {
      key: 'Notify',
      label: '通知配置',
      fields: [
        field({
          key: 'Notify.ServerChanKey',
          type: 'string',
          sensitive: true,
          label: 'ServerChan Key',
        }),
      ],
    },
  ],
}

const hsrBackendDecryptedModel = {
  SRA: {
    Id: 'hsr-account-plaintext-12345',
    Password: 'hsr-password-plaintext-67890',
  },
  Notify: {
    ServerChanKey: 'hsr-serverchan-key-plaintext-abcdef',
  },
}

const maaEndBackendDecryptedModel = {
  Info: {
    Name: 'test-user',
    Password: 'maaend-password-plaintext-12345',
    SklandToken: 'maaend-skland-token-plaintext-67890',
  },
  Notify: {
    ServerChanKey: 'maaend-serverchan-key-plaintext-abcdef',
  },
}

const testDir = fileURLToPath(new URL('.', import.meta.url))

const SchemaForm = compileSfcComponent(
  '../SchemaForm.vue',
  {
    vue,
    '@ant-design/icons-vue': {
      QuestionCircleOutlined: defineComponent({
        render: () => h('span', { class: 'icon-stub' }),
      }),
    },
    '@/composables/useSchemaFormModel': { useSchemaFormModel },
    '@/composables/useSensitiveFieldStrategy': sensitiveStrategy,
    '@/utils/schemaFormCore': schemaFormCore,
  },
  testDir
)

const FormStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h('form', attrs, slots.default?.())
  },
})

const FormItemStub = defineComponent({
  inheritAttrs: false,
  props: ['label', 'required', 'help', 'validateStatus'],
  setup(props, { attrs, slots }) {
    return () =>
      h('div', { class: 'form-item-stub', 'data-label': String(props.label ?? '') }, [
        h('label', {}, String(props.label ?? '')),
        slots.default?.(),
      ])
  },
})

const InputPasswordStub = defineComponent({
  inheritAttrs: false,
  props: ['value', 'placeholder', 'maxlength', 'disabled'],
  setup(props) {
    return () =>
      h('input', {
        type: 'password',
        class: 'a-input-password-stub',
        value: String(props.value ?? ''),
        placeholder: String(props.placeholder ?? ''),
        'data-disabled': props.disabled ? 'true' : 'false',
      })
  },
})

const InputStub = defineComponent({
  inheritAttrs: false,
  props: ['value', 'placeholder', 'maxlength', 'disabled'],
  setup(props) {
    return () =>
      h('input', {
        type: 'text',
        class: 'a-input-stub',
        value: String(props.value ?? ''),
        placeholder: String(props.placeholder ?? ''),
        'data-disabled': props.disabled ? 'true' : 'false',
      })
  },
})

const TextareaStub = defineComponent({
  inheritAttrs: false,
  props: ['value', 'placeholder', 'rows', 'disabled'],
  setup(props) {
    return () =>
      h('textarea', {
        class: 'a-textarea-stub',
        value: String(props.value ?? ''),
        placeholder: String(props.placeholder ?? ''),
      })
  },
})

const SwitchStub = defineComponent({
  inheritAttrs: false,
  props: ['checked', 'disabled'],
  setup(props) {
    return () =>
      h('span', {
        class: 'a-switch-stub',
        'data-checked': props.checked ? 'true' : 'false',
      })
  },
})

const ButtonStub = defineComponent({
  inheritAttrs: false,
  props: ['type', 'size', 'loading', 'disabled', 'danger'],
  setup(props, { attrs, slots }) {
    return () =>
      h(
        'button',
        {
          class: 'a-button-stub',
          'data-type': String(props.type ?? ''),
          'data-disabled': props.disabled ? 'true' : 'false',
          onClick: (attrs as any).onClick,
        },
        slots.default?.()
      )
  },
})

const TagStub = defineComponent({
  inheritAttrs: false,
  props: ['color'],
  setup(props, { slots }) {
    return () =>
      h('span', { class: 'a-tag-stub', 'data-color': String(props.color ?? '') }, slots.default?.())
  },
})

const SpaceStub = defineComponent({
  inheritAttrs: false,
  setup(_, { slots }) {
    return () => h('span', { class: 'a-space-stub' }, slots.default?.())
  },
})

const SpinStub = defineComponent({
  inheritAttrs: false,
  props: ['size'],
  setup() {
    return () => h('span', { class: 'a-spin-stub' }, '加载中')
  },
})

const TooltipStub = defineComponent({
  inheritAttrs: false,
  props: ['title'],
  setup(_, { slots }) {
    return () => h('span', { class: 'a-tooltip-stub' }, slots.default?.())
  },
})

const SelectStub = defineComponent({
  inheritAttrs: false,
  props: ['value', 'options', 'mode', 'disabled'],
  setup(props) {
    return () =>
      h('select', {
        class: 'a-select-stub',
        'data-value': String(props.value ?? ''),
        'data-disabled': props.disabled ? 'true' : 'false',
      })
  },
})

const InputNumberStub = defineComponent({
  inheritAttrs: false,
  props: ['value', 'min', 'max', 'step', 'disabled'],
  setup(props) {
    return () =>
      h('input', {
        type: 'number',
        class: 'a-input-number-stub',
        value: String(props.value ?? ''),
        'data-disabled': props.disabled ? 'true' : 'false',
      })
  },
})

const SliderStub = defineComponent({
  inheritAttrs: false,
  props: ['value', 'min', 'max', 'step', 'disabled'],
  setup(props) {
    return () =>
      h('input', {
        type: 'range',
        class: 'a-slider-stub',
        value: String(props.value ?? ''),
      })
  },
})

const TableStub = defineComponent({
  inheritAttrs: false,
  props: ['columns', 'dataSource', 'pagination', 'size', 'rowKey'],
  setup() {
    return () => h('table', { class: 'a-table-stub' })
  },
})

const AutoCompleteStub = defineComponent({
  inheritAttrs: false,
  props: ['value', 'options', 'disabled'],
  setup(props) {
    return () =>
      h('input', {
        type: 'text',
        class: 'a-autocomplete-stub',
        value: String(props.value ?? ''),
      })
  },
})

const collectInputValues = (root: FakeElement): string[] => {
  const values: string[] = []
  const walk = (node: FakeElement) => {
    if (!node) return
    if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {
      const v = node.attrs?.value ?? node.attrs?.['value'] ?? ''
      if (typeof v === 'string') values.push(v)
    }
    for (const child of (node.childNodes as FakeElement[]) || []) {
      walk(child)
    }
  }
  walk(root)
  return values
}

const collectPlaceholderAttr = (root: FakeElement, cls: string): string[] => {
  const placeholders: string[] = []
  const nodes = findAllByClass(root, cls)
  for (const n of nodes) {
    const ph = n.attrs?.placeholder
    if (typeof ph === 'string') placeholders.push(ph)
  }
  return placeholders
}

describe('SchemaForm mounted：HSR 真实 schema 敏感字段不泄漏明文', () => {
  let mountedApp: App<Element> | null = null

  beforeEach(() => {
    installDomStub(createDom())
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  it('HSR schema：组件挂载后敏感字段明文不出现在任何 input/textarea value 中', () => {
    const mounted = mountComponent(
      SchemaForm,
      {
        modelValue: hsrBackendDecryptedModel,
        schema: hsrUserSchema,
        layout: 'single',
      },
      {
        'a-form': FormStub,
        'a-form-item': FormItemStub,
        'a-input-password': InputPasswordStub,
        'a-input': InputStub,
        'a-textarea': TextareaStub,
        'a-switch': SwitchStub,
        'a-button': ButtonStub,
        'a-tag': TagStub,
        'a-space': SpaceStub,
        'a-spin': SpinStub,
        'a-tooltip': TooltipStub,
        'a-select': SelectStub,
        'a-input-number': InputNumberStub,
        'a-slider': SliderStub,
        'a-table': TableStub,
        'a-auto-complete': AutoCompleteStub,
      }
    )
    mountedApp = mounted.app

    const inputValues = collectInputValues(mounted.container)
    const joined = inputValues.join('\n')

    // 敏感字段明文绝不能进入 DOM value
    expect(joined).not.toContain('hsr-account-plaintext-12345')
    expect(joined).not.toContain('hsr-password-plaintext-67890')
    expect(joined).not.toContain('hsr-serverchan-key-plaintext-abcdef')

    // 三个敏感字段都应渲染 input-password stub
    const passwordInputs = findAllByClass(mounted.container, 'a-input-password-stub')
    expect(passwordInputs.length).toBeGreaterThanOrEqual(3)
  })

  it('HSR schema：渲染"敏感"标签 + placeholder 不含明文', () => {
    const mounted = mountComponent(
      SchemaForm,
      {
        modelValue: hsrBackendDecryptedModel,
        schema: hsrUserSchema,
        layout: 'single',
      },
      {
        'a-form': FormStub,
        'a-form-item': FormItemStub,
        'a-input-password': InputPasswordStub,
        'a-input': InputStub,
        'a-textarea': TextareaStub,
        'a-switch': SwitchStub,
        'a-button': ButtonStub,
        'a-tag': TagStub,
        'a-space': SpaceStub,
        'a-spin': SpinStub,
        'a-tooltip': TooltipStub,
        'a-select': SelectStub,
        'a-input-number': InputNumberStub,
        'a-slider': SliderStub,
        'a-table': TableStub,
        'a-auto-complete': AutoCompleteStub,
      }
    )
    mountedApp = mounted.app

    // 应该出现 3 个 color="gold" 的"敏感"标签（SRA.Id / SRA.Password / Notify.ServerChanKey）
    const tagStubs = findAllByClass(mounted.container, 'a-tag-stub')
    const sensitiveTags = tagStubs.filter(n => n.attrs?.['data-color'] === 'gold')
    expect(sensitiveTags.length).toBe(3)

    // 敏感字段 placeholder 不含明文
    const placeholders = collectPlaceholderAttr(mounted.container, 'a-input-password-stub')
    const phJoined = placeholders.join('\n')
    expect(phJoined).not.toContain('hsr-account-plaintext')
    expect(phJoined).not.toContain('hsr-password-plaintext')
    expect(phJoined).not.toContain('hsr-serverchan-key-plaintext')
  })
})

describe('SchemaForm mounted：MaaEnd 真实 schema 敏感字段不泄漏明文', () => {
  let mountedApp: App<Element> | null = null

  beforeEach(() => {
    installDomStub(createDom())
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  it('MaaEnd schema：组件挂载后敏感字段明文不出现在 DOM 中', () => {
    const mounted = mountComponent(
      SchemaForm,
      {
        modelValue: maaEndBackendDecryptedModel,
        schema: maaEndUserSchema,
        layout: 'single',
      },
      {
        'a-form': FormStub,
        'a-form-item': FormItemStub,
        'a-input-password': InputPasswordStub,
        'a-input': InputStub,
        'a-textarea': TextareaStub,
        'a-switch': SwitchStub,
        'a-button': ButtonStub,
        'a-tag': TagStub,
        'a-space': SpaceStub,
        'a-spin': SpinStub,
        'a-tooltip': TooltipStub,
        'a-select': SelectStub,
        'a-input-number': InputNumberStub,
        'a-slider': SliderStub,
        'a-table': TableStub,
        'a-auto-complete': AutoCompleteStub,
      }
    )
    mountedApp = mounted.app

    const inputValues = collectInputValues(mounted.container)
    const joined = inputValues.join('\n')

    expect(joined).not.toContain('maaend-password-plaintext-12345')
    expect(joined).not.toContain('maaend-skland-token-plaintext-67890')
    expect(joined).not.toContain('maaend-serverchan-key-plaintext-abcdef')

    // 非敏感字段 Info.Name 应正常显示
    expect(joined).toContain('test-user')

    // 三个敏感字段（Password / SklandToken / ServerChanKey）应渲染为 input-password
    const passwordInputs = findAllByClass(mounted.container, 'a-input-password-stub')
    expect(passwordInputs.length).toBe(3)
  })

  it('MaaEnd schema：3 个"敏感"标签 + 3 个 input-password placeholder 不含明文', () => {
    const mounted = mountComponent(
      SchemaForm,
      {
        modelValue: maaEndBackendDecryptedModel,
        schema: maaEndUserSchema,
        layout: 'single',
      },
      {
        'a-form': FormStub,
        'a-form-item': FormItemStub,
        'a-input-password': InputPasswordStub,
        'a-input': InputStub,
        'a-textarea': TextareaStub,
        'a-switch': SwitchStub,
        'a-button': ButtonStub,
        'a-tag': TagStub,
        'a-space': SpaceStub,
        'a-spin': SpinStub,
        'a-tooltip': TooltipStub,
        'a-select': SelectStub,
        'a-input-number': InputNumberStub,
        'a-slider': SliderStub,
        'a-table': TableStub,
        'a-auto-complete': AutoCompleteStub,
      }
    )
    mountedApp = mounted.app

    const tagStubs = findAllByClass(mounted.container, 'a-tag-stub')
    const sensitiveTags = tagStubs.filter(n => n.attrs?.['data-color'] === 'gold')
    expect(sensitiveTags.length).toBe(3)

    const placeholders = collectPlaceholderAttr(mounted.container, 'a-input-password-stub')
    expect(placeholders.length).toBe(3)
    const phJoined = placeholders.join('\n')
    expect(phJoined).not.toContain('maaend-password-plaintext')
    expect(phJoined).not.toContain('maaend-skland-token-plaintext')
    expect(phJoined).not.toContain('maaend-serverchan-key-plaintext')
  })
})

describe('SchemaForm mounted：通用 schema 非敏感字段正常渲染', () => {
  let mountedApp: App<Element> | null = null

  beforeEach(() => {
    installDomStub(createDom())
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  it('通用 schema：非敏感字符串字段值进入 DOM，无"敏感"标签', () => {
    const genericSchema: SchemaDefinition = {
      groups: [
        {
          key: 'Info',
          label: '基础信息',
          fields: [
            field({ key: 'Info.Name', type: 'string', label: '用户名' }),
            field({ key: 'Info.Notes', type: 'string', label: '备注' }),
          ],
        },
      ],
    }
    const model = { Info: { Name: 'alice', Notes: 'some-notes' } }

    const mounted = mountComponent(
      SchemaForm,
      {
        modelValue: model,
        schema: genericSchema,
        layout: 'single',
      },
      {
        'a-form': FormStub,
        'a-form-item': FormItemStub,
        'a-input-password': InputPasswordStub,
        'a-input': InputStub,
        'a-textarea': TextareaStub,
        'a-switch': SwitchStub,
        'a-button': ButtonStub,
        'a-tag': TagStub,
        'a-space': SpaceStub,
        'a-spin': SpinStub,
        'a-tooltip': TooltipStub,
        'a-select': SelectStub,
        'a-input-number': InputNumberStub,
        'a-slider': SliderStub,
        'a-table': TableStub,
        'a-auto-complete': AutoCompleteStub,
      }
    )
    mountedApp = mounted.app

    const inputValues = collectInputValues(mounted.container)
    const joined = inputValues.join('\n')

    // 非敏感字段值应正常出现在 DOM 中
    expect(joined).toContain('alice')
    expect(joined).toContain('some-notes')

    // 不应有"敏感"标签
    const tagStubs = findAllByClass(mounted.container, 'a-tag-stub')
    const sensitiveTags = tagStubs.filter(n => n.attrs?.['data-color'] === 'gold')
    expect(sensitiveTags.length).toBe(0)

    // 不应出现 input-password stub
    const passwordInputs = findAllByClass(mounted.container, 'a-input-password-stub')
    expect(passwordInputs.length).toBe(0)
  })
})
