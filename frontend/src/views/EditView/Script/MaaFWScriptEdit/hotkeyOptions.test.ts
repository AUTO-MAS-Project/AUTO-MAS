import { describe, expect, it } from 'vitest'

import type { MaaFWInterfacePreviewData, MaaFWOptionInfo } from '@/types/script'
import {
  collectHotkeyOptions,
  countChangedHotkeys,
  effectiveHotkeyValues,
  hotkeySettingDescription,
  mergeHotkeyMap,
  parseHotkeyMap,
} from './hotkeyOptions'

const option = (name: string, overrides: Partial<MaaFWOptionInfo> = {}): MaaFWOptionInfo => ({
  name,
  type: 'hotkey',
  label: name,
  controller: [],
  resource: [],
  cases: [],
  inputs: [],
  hotkeys: [],
  ...overrides,
})

const keymapGeneral = option('KeymapGeneral', {
  hotkeys: [
    { name: 'UseTool', label: '使用当前便捷工具', default: 'R' },
    { name: 'Interact', label: '交互', default: 'F' },
  ],
})
const keymapFight = option('KeymapFight', {
  hotkeys: [
    { name: 'Combo', label: '释放连携技', default: 'E' },
    { name: 'Skill1', label: '1号干员战技', default: '1' },
  ],
})

const preview = (overrides: Partial<MaaFWInterfacePreviewData> = {}): MaaFWInterfacePreviewData =>
  ({
    path: '',
    project: { name: 'p' },
    globalOption: ['KeymapFight', 'KeymapGeneral'],
    controlCapabilities: { emulatorExtras: {} },
    controllers: [{ name: 'Win', type: 'Win32', option: [], permissionRequired: false }],
    resources: [{ name: 'Official', path: [], controller: [], option: [] }],
    groups: [],
    settings: [
      {
        name: 'Keymap',
        description: '与游戏中 设置-按键 保持一致',
        option: ['KeymapGeneral', 'KeymapFight'],
        defaultExpand: false,
      },
    ],
    tasks: [],
    options: [keymapFight, keymapGeneral],
    presets: [],
    importCount: 0,
    agentCount: 0,
    ...overrides,
  }) as MaaFWInterfacePreviewData

describe('collectHotkeyOptions', () => {
  it('按 settings 顺序列出 globalOption 里的 hotkey option', () => {
    expect(collectHotkeyOptions(preview(), 'Win', 'Official').map(item => item.name)).toEqual([
      'KeymapGeneral',
      'KeymapFight',
    ])
  })

  it('没有预览或没有 hotkey option 时为空', () => {
    expect(collectHotkeyOptions(null, 'Win', 'Official')).toEqual([])
    expect(
      collectHotkeyOptions(
        preview({ globalOption: [], options: [option('Plain', { type: 'switch' })] }),
        'Win',
        'Official'
      )
    ).toEqual([])
  })

  it('按 option 自身的 controller / resource 过滤', () => {
    const data = preview({
      options: [
        option('KeymapFight', { ...keymapFight, controller: ['Adb'] }),
        option('KeymapGeneral', { ...keymapGeneral, resource: ['Bilibili'] }),
      ],
    })
    expect(collectHotkeyOptions(data, 'Win', 'Official')).toEqual([])
    expect(collectHotkeyOptions(data, 'Win', 'Bilibili').map(item => item.name)).toEqual([
      'KeymapGeneral',
    ])
  })

  it('资源、控制器、适用任务与 cases 子选项里的 hotkey option 都收进来', () => {
    const data = preview({
      globalOption: [],
      settings: [],
      resources: [{ name: 'Official', path: [], controller: [], option: ['FromResource'] }],
      controllers: [
        { name: 'Win', type: 'Win32', option: ['FromController'], permissionRequired: false },
      ],
      tasks: [
        {
          name: 'Fight',
          entry: 'Fight',
          group: [],
          controller: [],
          resource: [],
          option: ['Mode'],
          defaultCheck: true,
        },
        {
          name: 'AdbOnly',
          entry: 'AdbOnly',
          group: [],
          controller: ['Adb'],
          resource: [],
          option: ['AdbKeys'],
          defaultCheck: true,
        },
      ],
      options: [
        option('FromResource', { hotkeys: [{ name: 'A', default: 'A' }] }),
        option('FromController', { hotkeys: [{ name: 'B', default: 'B' }] }),
        option('Mode', {
          type: 'select',
          cases: [{ name: 'On', option: ['Nested'] }],
        }),
        option('Nested', { hotkeys: [{ name: 'C', default: 'C' }] }),
        option('AdbKeys', { hotkeys: [{ name: 'D', default: 'D' }] }),
      ],
    })
    expect(collectHotkeyOptions(data, 'Win', 'Official').map(item => item.name)).toEqual([
      'FromResource',
      'FromController',
      'Nested',
    ])
  })
})

describe('hotkeySettingDescription', () => {
  it('只有一个带描述的 setting 时用它', () => {
    const data = preview()
    expect(hotkeySettingDescription(data, collectHotkeyOptions(data, 'Win', 'Official'))).toBe(
      '与游戏中 设置-按键 保持一致'
    )
    expect(hotkeySettingDescription(preview({ settings: [] }), [keymapGeneral])).toBe('')
  })
})

describe('Game.Hotkeys 读写', () => {
  it('不是合法 JSON 当空', () => {
    expect(parseHotkeyMap('not json')).toEqual({})
    expect(parseHotkeyMap('[]')).toEqual({})
    expect(parseHotkeyMap(undefined)).toEqual({})
    expect(parseHotkeyMap('{"A":{"x":"Q","y":1},"B":"bad"}')).toEqual({ A: { x: 'Q' } })
  })

  it('生效值取存的值，没有就是默认值；已改数只算与默认不同的字段', () => {
    const options = [keymapGeneral, keymapFight]
    const stored = parseHotkeyMap('{"KeymapFight":{"Combo":"Q","Skill1":"1"}}')
    const values = effectiveHotkeyValues(options, stored)
    expect(values).toEqual({
      KeymapGeneral: { UseTool: 'R', Interact: 'F' },
      KeymapFight: { Combo: 'Q', Skill1: '1' },
    })
    expect(countChangedHotkeys(options, stored)).toBe(1)
    expect(countChangedHotkeys(options, values)).toBe(1)
  })

  it('保存只替换展示的 option，与默认相同的字段不存，空 option 删掉', () => {
    const existing = {
      KeymapFight: { Combo: 'Q' },
      Hidden: { X: 'Ctrl+A' },
    }
    const merged = mergeHotkeyMap(existing, [keymapGeneral, keymapFight], {
      KeymapGeneral: { UseTool: 'Shift+R', Interact: 'F' },
      KeymapFight: { Combo: 'e', Skill1: '1' },
    })
    expect(merged).toEqual({
      KeymapGeneral: { UseTool: 'Shift+R' },
      Hidden: { X: 'Ctrl+A' },
    })
  })
})
