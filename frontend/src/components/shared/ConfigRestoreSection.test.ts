// @vitest-environment vue-client
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { defineComponent, h, nextTick, ref, type Component } from 'vue'
import { createI18n } from 'vue-i18n'
import { Service, type ConfigBackupPreviewOut, type ConfigBackupRestoreOut } from '@/api'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'
import type { ConfirmOptions } from '@/composables/useConfirm'
import LegacyRestore from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { deferred, testView } from '../../../tests/vueRenderer'
import SharedRestore from './ConfigRestoreSection.vue'

const confirm = vi.hoisted(() => vi.fn<(options: ConfirmOptions) => Promise<boolean>>())
vi.mock('@/composables/useConfirm', () => ({ useConfirm: () => ({ confirm }) }))
vi.mock('@/components/ui', () => ({
  AppModal: defineComponent({
    props: ['open', 'title'],
    emits: ['update:open'],
    setup:
      (props, { slots, emit }) =>
      () =>
        props.open &&
        h('section', [
          slots.header?.(),
          slots.default?.(),
          slots['footer-left']?.(),
          h(
            'button',
            { onClick: () => emit('update:open', false) },
            'close ' + (props.title ?? 'preview')
          ),
        ]),
  }),
}))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const time = '20261125_101112'
const list = () =>
  vi.spyOn(Service, 'listConfigBackupsApiApiScriptsBackupListGet').mockResolvedValue({
    code: 200,
    data: [{ time }],
  })
const previewResponse = (name: string) => ({ code: 200, target: 'a', time, data: { name } })
const timestamp = '2026-11-25 10:11:12'

function mount(component: Component = SharedRestore) {
  const user = ref<string | null>(null)
  const open = ref(true)
  const detail = vi.fn().mockResolvedValue(true)
  const restored = vi.fn()
  const view = testView(
    defineComponent({
      setup() {
        const { restoreApi } = useConfigBackupApi({
          scriptId: 's',
          userId: user,
          logger: { error: vi.fn() },
        })
        return () =>
          h(
            component,
            {
              scriptId: 's',
              userId: user.value,
              open: open.value,
              'onUpdate:open': (value: boolean) => {
                open.value = value
              },
              targets: [
                { key: 'a', kind: 'script' },
                { key: 'b', kind: 'user' },
              ],
              scriptName: 'Demo',
              api: restoreApi,
              onRestored: restored,
              onDetail: detail,
            },
            {
              'preview-title': ({ time }: { time: string }) => 'Title ' + time,
              preview: ({ target, raw }: { target: string; raw: { name: string } | null }) =>
                'Summary ' + target + ' ' + (raw?.name ?? ''),
            }
          )
      },
    })
  )
  const pass = defineComponent({
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  })
  for (const name of [
    'AAlert',
    'AListItem',
    'ATag',
    'ASpace',
    'ASpin',
    'ATooltip',
    'NoData',
    'ACollapse',
    'ACollapsePanel',
    'ADescriptions',
    'ADescriptionsItem',
  ]) {
    view.app.component(name, pass)
  }
  view.app.component(
    'AButton',
    defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          h('button', slots.default?.()),
    })
  )
  view.app.component(
    'AList',
    defineComponent({
      props: ['dataSource'],
      setup:
        (props, { slots }) =>
        () =>
          h(
            'div',
            props.dataSource.map((item: unknown) => slots.renderItem?.({ item }))
          ),
    })
  )
  view.app.component(
    'ASegmented',
    defineComponent({
      props: ['options'],
      emits: ['update:value'],
      setup:
        (props, { emit }) =>
        () =>
          h(
            'div',
            props.options.map(({ value }: { value: string }) =>
              h('button', { onClick: () => emit('update:value', value) }, 'target ' + value)
            )
          ),
    })
  )
  view.app.use(
    createI18n({
      legacy: false,
      locale: 'en',
      messages: { en: {} },
      missingWarn: false,
      fallbackWarn: false,
    })
  )
  view.mount()
  async function click(label: string) {
    const button = view.all().find(el => el.tag === 'button' && view.text(el) === label)
    expect(button, label).toBeDefined()
    ;(button!.props.onClick as () => void)()
    await nextTick()
  }
  return { ...view, click, user, open, detail, restored }
}

beforeEach(() => {
  confirm.mockReset()
})
afterEach(() => {
  vi.restoreAllMocks()
})

describe('配置恢复', () => {
  it('旧入口透传预览和标题插槽、详情回调及弹窗开关', async () => {
    const listed = list()
    const preview = vi
      .spyOn(Service, 'getConfigBackupPreviewApiApiScriptsBackupPreviewGet')
      .mockResolvedValue(previewResponse('first'))
    const view = mount(LegacyRestore)
    try {
      await vi.waitFor(() => expect(view.text()).toContain(timestamp))
      expect(listed).toHaveBeenCalledWith('s', 'a', null)
      await view.click('core.edit.configRestorePreview')
      await vi.waitFor(() => expect(view.text()).toContain('Summary a first'))
      expect(view.text()).toContain('Title ' + timestamp)
      expect(preview).toHaveBeenCalledWith('s', time, 'a', null)
      await view.click('core.edit.configRestoreDetailView')
      expect(view.detail).toHaveBeenCalledWith('a', { time }, null)
      await view.click('close core.edit.configRestoreTitle')
      expect(view.open.value).toBe(false)
    } finally {
      view.app.unmount()
    }
  })

  it('损坏备份只有在同一目标的二次确认后才强制恢复', async () => {
    list()
    const restore = vi
      .spyOn(Service, 'restoreConfigBackupApiApiScriptsBackupRestorePost')
      .mockResolvedValueOnce({ code: 409, target: 'a', message: 'damaged' })
      .mockResolvedValueOnce({ code: 409, target: 'a', message: 'damaged' })
      .mockResolvedValue({ code: 200, target: 'a' })
    const view = mount(LegacyRestore)
    try {
      await vi.waitFor(() => expect(view.text()).toContain(timestamp))
      await view.click('core.edit.configRestoreAction')
      expect(restore).not.toHaveBeenCalled()
      await confirm.mock.lastCall![0].onOk!()
      const stale = confirm.mock.lastCall![0]
      expect(restore.mock.calls[0][0]).toEqual({ scriptId: 's', userId: null, target: 'a', time })
      await view.click('target b')
      await view.click('target a')
      await stale.onOk!()
      expect(restore).toHaveBeenCalledTimes(1)
      await vi.waitFor(() => expect(view.text()).toContain(timestamp))
      await view.click('core.edit.configRestoreAction')
      await confirm.mock.lastCall![0].onOk!()
      expect(view.restored).not.toHaveBeenCalled()
      await confirm.mock.lastCall![0].onOk!()
      expect(restore.mock.lastCall![0]).toEqual({
        scriptId: 's',
        userId: null,
        target: 'a',
        time,
        force: true,
      })
      expect(view.restored).toHaveBeenCalledWith('a', { time })
    } finally {
      view.app.unmount()
    }
  })

  it('新账号的预览先完成，迟到的旧摘要和恢复回调不能污染当前账号', async () => {
    list()
    const previous = deferred<ConfigBackupPreviewOut>()
    vi.spyOn(Service, 'getConfigBackupPreviewApiApiScriptsBackupPreviewGet')
      .mockReturnValueOnce(previous.promise)
      .mockResolvedValue(previewResponse('new account'))
    const pending = deferred<ConfigBackupRestoreOut>()
    vi.spyOn(Service, 'restoreConfigBackupApiApiScriptsBackupRestorePost').mockReturnValue(
      pending.promise
    )
    const view = mount()
    try {
      await vi.waitFor(() => expect(view.text()).toContain(timestamp))
      await view.click('core.edit.configRestoreAction')
      const restoring = confirm.mock.lastCall![0].onOk!()
      await view.click('core.edit.configRestorePreview')
      view.user.value = 'new'
      await nextTick()
      await vi.waitFor(() => expect(view.text()).toContain(timestamp))
      await view.click('core.edit.configRestorePreview')
      await vi.waitFor(() => expect(view.text()).toContain('new account'))
      previous.resolve(previewResponse('old account'))
      pending.resolve({ code: 200, target: 'a' })
      await restoring
      await nextTick()
      expect(view.text()).not.toContain('old account')
      expect(view.restored).not.toHaveBeenCalled()
    } finally {
      view.app.unmount()
    }
  })
})
