import { describe, expect, it } from 'vitest'
import {
  buildCreateRequest,
  buildCreateSteps,
  createScriptTypeOptions,
  filterScriptTypeOptions,
  SCRIPT_TYPE_OPTIONS,
  splitScriptTypeOptions,
} from './scriptCreateFlow'

describe('scriptCreateFlow', () => {
  it('starts with script type and adds the config step only for General scripts', () => {
    expect(buildCreateSteps({ type: 'General' }).map(step => step.key)).toEqual(['type', 'config'])
    expect(buildCreateSteps({ type: 'MaaFW' }).map(step => step.key)).toEqual(['type'])
  })

  it('places General before specialized adapters', () => {
    expect(SCRIPT_TYPE_OPTIONS[0].value).toBe('General')
  })

  it('filters script types by aliases and group', () => {
    expect(filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, '1999')).toEqual([])
  })

  it('places General and MaaFW in the general section', () => {
    const sections = splitScriptTypeOptions(SCRIPT_TYPE_OPTIONS)
    expect(sections.specialized.map(item => item.value)).not.toContain('General')
    expect(sections.specialized.map(item => item.value)).not.toContain('MaaFW')
    expect(sections.specialized.map(item => item.value)).not.toContain('Okww')
    expect(sections.general.map(item => item.value)).toEqual(['General', 'MaaFW'])
  })

  it('builds create options from available registry descriptors', () => {
    const options = createScriptTypeOptions([
      {
        type_key: 'PluginScript',
        display_name: '插件脚本',
        editor_kind: 'plugin:example',
        supported_modes: ['daily'],
        script_schema: {},
        user_schema: {},
        is_builtin: false,
        available: true,
        client: {
          create: {
            description: '来自插件声明的创建说明',
            keywords: ['插件别名'],
          },
        },
      },
      {
        type_key: 'DisabledScript',
        display_name: '未启用脚本',
        editor_kind: 'plugin:disabled',
        supported_modes: [],
        script_schema: {},
        user_schema: {},
        is_builtin: false,
        available: false,
      },
      {
        type_key: 'M9A',
        display_name: 'M9A 脚本',
        editor_kind: 'plugin:automas_script_maafw',
        icon_url: 'https://example.test/m9a.png',
        supported_modes: [],
        script_schema: {},
        user_schema: {},
        is_builtin: false,
        available: true,
        create_group: 'specialized',
        client: {
          create: {
            description: '重返未来：1999 自动化脚本',
            keywords: ['m9a', '1999', '重返未来'],
          },
        },
      },
      {
        type_key: 'ReadOnlyScript',
        display_name: '只读脚本',
        editor_kind: 'plugin:readonly',
        supported_modes: [],
        script_schema: {},
        user_schema: {},
        is_builtin: false,
        available: true,
        creatable: false,
      },
      {
        type_key: 'MaaFW',
        display_name: 'MaaFramework 项目',
        editor_kind: 'builtin:maafw',
        supported_modes: [],
        script_schema: {},
        user_schema: {},
        is_builtin: true,
        available: true,
        create_group: 'general',
      },
    ])

    expect(options).toHaveLength(3)
    expect(options[0]).toMatchObject({
      value: 'PluginScript',
      title: '插件脚本',
      description: '来自插件声明的创建说明',
      group: 'specialized',
    })
    expect(options[0].keywords).toContain('插件别名')
    expect(options[1]).toMatchObject({
      value: 'M9A',
      title: 'M9A 脚本',
      description: '重返未来：1999 自动化脚本',
      group: 'specialized',
      icon: 'https://example.test/m9a.png',
    })
    expect(options[1].keywords).toContain('1999')
    expect(options[2]).toMatchObject({
      value: 'MaaFW',
      group: 'general',
    })
  })

  it('builds submit requests only when required selections exist', () => {
    expect(
      buildCreateRequest({
        type: 'SRC',
        configMode: 'template',
        template: null,
      })
    ).toEqual({ kind: 'new', type: 'SRC' })

    expect(
      buildCreateRequest({
        type: 'General',
        configMode: 'custom',
        template: null,
      })
    ).toEqual({ kind: 'general-custom' })

    expect(
      buildCreateRequest({
        type: 'General',
        configMode: 'template',
        template: null,
      })
    ).toBeNull()
  })
})
