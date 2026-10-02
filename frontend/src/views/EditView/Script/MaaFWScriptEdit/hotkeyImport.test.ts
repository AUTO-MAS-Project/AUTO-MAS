import { describe, expect, it } from 'vitest'

import type { MaaFWInterfacePreviewData, MaaFWOptionInfo } from '@/types/script'
import {
  allHotkeyOptions,
  collectHotkeyImportCandidates,
  hasShellInstanceHotkeys,
  importHotkeyValues,
  mergeImportedHotkeys,
  restrictHotkeys,
  type MaaFWShellHotkeySource,
} from './hotkeyImport'
import type { MaaFWHotkeyMap } from './hotkeyOptions'

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
    { name: 'UseTool', default: 'R' },
    { name: 'Interact', default: 'F' },
  ],
})
const keymapFight = option('KeymapFight', {
  hotkeys: [
    { name: 'Combo', default: 'E' },
    { name: 'Skill1', default: '1' },
  ],
})
const options = [keymapGeneral, keymapFight]

const instance = (
  id: string,
  hotkeys: MaaFWHotkeyMap | undefined,
  overrides: Partial<MaaFWShellHotkeySource> = {}
): MaaFWShellHotkeySource =>
  ({ id, name: id, source: 'MXU', active: false, hotkeys, ...overrides }) as MaaFWShellHotkeySource

describe('restrictHotkeys', () => {
  it('只留展示的 option 里声明过的字段、非空的值', () => {
    expect(
      restrictHotkeys(
        {
          KeymapGeneral: { UseTool: 'Q', Unknown: 'Z', Interact: '  ' },
          KeymapFight: { Combo: '' },
          NotShown: { A: 'B' },
        },
        options
      )
    ).toEqual({ KeymapGeneral: { UseTool: 'Q' } })
  })
})

describe('collectHotkeyImportCandidates', () => {
  it('限定展示字段后为空的实例不算候选', () => {
    expect(
      collectHotkeyImportCandidates(
        [instance('a', { NotShown: { A: 'B' } }), instance('b', undefined), instance('c', {})],
        options
      )
    ).toEqual([])
  })

  it('内容相同的合并成一个（别名、大小写、修饰键顺序不算差别；展示之外的字段不参与比较）', () => {
    const candidates = collectHotkeyImportCandidates(
      [
        instance('a', { KeymapFight: { Combo: 'shift+ctrl+e' } }),
        instance('b', { KeymapFight: { Combo: 'Ctrl+Shift+E' }, NotShown: { A: 'X' } }),
        instance('c', { KeymapFight: { Combo: 'Q' } }),
      ],
      options
    )
    expect(candidates.map(item => item.id)).toEqual(['a', 'c'])
    expect(candidates[0].hotkeys).toEqual({ KeymapFight: { Combo: 'shift+ctrl+e' } })
  })

  it('外壳上次使用的那份排第一，合并组里有它时用它的名字', () => {
    const candidates = collectHotkeyImportCandidates(
      [
        instance('a', { KeymapFight: { Combo: 'Q' } }),
        instance(
          'b',
          { KeymapFight: { Combo: 'G' } },
          {
            source: 'MFAAvalonia' as MaaFWShellHotkeySource['source'],
          }
        ),
        instance('c', { KeymapFight: { Combo: 'G' } }, { active: true, name: '主号' }),
      ],
      options
    )
    expect(
      candidates.map(({ id, name, source, active }) => ({ id, name, source, active }))
    ).toEqual([
      { id: 'c', name: '主号', source: 'MFAAvalonia', active: true },
      { id: 'a', name: 'a', source: 'MXU', active: false },
    ])
  })

  it('MXU 所有实例共用全局键位时只剩一个候选', () => {
    const shared = { KeymapGeneral: { UseTool: 'R' }, KeymapFight: { Combo: 'E', Skill1: '1' } }
    const candidates = collectHotkeyImportCandidates(
      ['1', '2', '3'].map(id => instance(id, shared, { active: id === '3' })),
      options
    )
    expect(candidates).toHaveLength(1)
    expect(candidates[0]).toMatchObject({ id: '3', active: true })
  })
})

describe('importHotkeyValues', () => {
  it('有值且支持的归一后填入并计数，不支持的跳过计数；修饰键个数不符照样填', () => {
    const fight = option('KeymapFight', {
      hotkeys: [
        { name: 'Combo', default: 'E', modifierCount: 0 },
        { name: 'Skill1', default: '1' },
      ],
    })
    const result = importHotkeyValues([keymapGeneral, fight], {
      KeymapGeneral: { UseTool: 'esc', Interact: 'MouseLeft' },
      KeymapFight: { Combo: 'shift+ctrl+g', Skill1: '' },
      NotShown: { A: 'B' },
    })
    expect(result).toEqual({
      values: {
        KeymapGeneral: { UseTool: 'Escape' },
        KeymapFight: { Combo: 'Ctrl+Shift+G' },
      },
      applied: 2,
      skipped: 1,
    })
  })
})

describe('引导写入脚本', () => {
  it('引导取导入候选的第一份：外壳上次使用的优先，否则按选中顺序第一份带键位的', () => {
    const options = [option('KeymapFight', { hotkeys: [{ name: 'Combo', default: 'E' }] })]
    const pick = (selected: MaaFWShellHotkeySource[]) =>
      collectHotkeyImportCandidates(selected, options)[0]?.hotkeys ?? null
    const a = instance('a', {})
    const b = instance('b', { KeymapFight: { Combo: 'Q' } })
    const c = instance('c', { KeymapFight: { Combo: 'G' } })
    expect(pick([a, b, c])).toEqual({ KeymapFight: { Combo: 'Q' } })
    expect(pick([a, b, { ...c, active: true }])).toEqual({ KeymapFight: { Combo: 'G' } })
    // 上次使用的那份没键位：退回第一份带键位的
    expect(pick([{ ...a, active: true }, c])).toEqual({ KeymapFight: { Combo: 'G' } })
    expect(pick([a])).toBeNull()
    expect(hasShellInstanceHotkeys(a)).toBe(false)
    expect(hasShellInstanceHotkeys(b)).toBe(true)
  })

  it('allHotkeyOptions：不按控制器 / 资源过滤，只挑有字段的 hotkey option', () => {
    const preview = {
      options: [
        keymapFight,
        option('Empty', { hotkeys: [] }),
        option('Select', { type: 'select', hotkeys: [] }),
        option('AdbOnly', { controller: ['Adb'], hotkeys: [{ name: 'K', default: 'K' }] }),
      ],
    } as unknown as MaaFWInterfacePreviewData
    expect(allHotkeyOptions(preview).map(item => item.name)).toEqual(['KeymapFight', 'AdbOnly'])
    expect(allHotkeyOptions(null)).toEqual([])
  })

  it('mergeImportedHotkeys：只存与默认不同的字段，保留已有的其他 option 条目与没导入的字段', () => {
    const existing: MaaFWHotkeyMap = {
      KeymapGeneral: { Interact: 'G' },
      Other: { X: 'Y' },
    }
    const merged = mergeImportedHotkeys(existing, options, {
      KeymapGeneral: { UseTool: 'Q' },
      // 与默认相同：不存
      KeymapFight: { Combo: 'e', Skill1: 'MouseLeft' },
    })
    expect(merged).toEqual({
      KeymapGeneral: { UseTool: 'Q', Interact: 'G' },
      Other: { X: 'Y' },
    })
  })

  it('mergeImportedHotkeys：导入里没有可用的值时原样返回', () => {
    const existing: MaaFWHotkeyMap = { KeymapFight: { Combo: 'Q' } }
    expect(mergeImportedHotkeys(existing, options, { KeymapFight: { Combo: 'MouseLeft' } })).toBe(
      existing
    )
  })
})
