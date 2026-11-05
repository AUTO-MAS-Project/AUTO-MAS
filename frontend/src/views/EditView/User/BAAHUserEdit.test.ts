import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import messages from '../../../../../res/i18n/en.json'
import BAAHUserEdit from './BAAHUserEdit.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { scriptId: 'managed-script', userId: 'account' } }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))
vi.mock('@/router', () => ({ navigateTo: vi.fn() }))
vi.mock('@/composables/useScriptConfigLock', () => ({
  useScriptConfigLock: () => ({ configLocked: ref(false) }),
}))
vi.mock('@/composables/useUserApi.ts', () => ({
  useUserApi: () => ({ loading: ref(false), error: ref(null) }),
}))
vi.mock('@/composables/useScriptApi.ts', () => ({
  useScriptApi: () => ({ error: ref(null) }),
}))
vi.mock('@/composables/useConfigBackupApi', () => ({
  useConfigBackupApi: () => ({ restoreApi: {}, ensureBackup: vi.fn() }),
}))
vi.mock('@/components/ConfigLockPanel.vue', () => ({
  default: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  }),
}))
vi.mock('@/components/UserEditHeader.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/UserNotifyConfig.vue', () => ({ default: { render: () => null } }))
vi.mock('@/views/EditView/User/components/ConfigRestoreSection.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/views/EditView/User/components/UserNameField.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/views/EditView/User/components/UserStatusField.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/views/EditView/User/components/UserRemainedDayField.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/views/EditView/User/components/UserNotesField.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/components/FieldLabelWithHint.vue', () => ({
  default: defineComponent({ props: ['text'], setup: props => () => h('label', props.text) }),
}))

describe('BAAH configuration guidance', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn() }) },
    })
  })

  it('keeps real configuration controls without offering ineffective source or override modes', async () => {
    const app = createSSRApp(BAAHUserEdit)
    app.use(createI18n({ legacy: false, locale: 'en', flatJson: true, messages: { en: messages } }))
    const container = defineComponent({
      props: ['message'],
      setup:
        (props, { slots }) =>
        () =>
          h('div', [props.message, slots.label?.(), slots.default?.()]),
    })
    for (const name of [
      'ACard',
      'AForm',
      'AFormItem',
      'ARow',
      'ACol',
      'AAlert',
      'AButton',
      'ASelect',
      'ASelectOption',
      'AInput',
      'ATag',
      'ARadioGroup',
      'ARadio',
      'ATooltip',
    ]) {
      app.component(name, container)
    }
    const html = await renderToString(app)
    expect(html).toContain('Tasks use the selected BAAH configuration file')
    expect(html).toContain('Stage plan')
    expect(html).toContain('Event')
    expect(html).not.toContain('Configuration management')
    expect(html).not.toContain('Enable overriding the standard configuration')
  })
})
