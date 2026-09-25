import { describe, expect, it } from 'vitest'

import type { HSRManagedField } from '@/composables/useHSRPluginApi'
import {
  canResetField,
  findEnabledBuildTargetField,
  formatManagedValue,
  isFieldVisible,
  isRowListField,
  listFieldToRows,
  rowsToListField,
  splitFieldsByGroup,
  summarizeOverriddenFields,
} from './managedFields'

const field = (key: string, extra: Partial<HSRManagedField> = {}): HSRManagedField => ({
  key,
  label: key,
  type: 'string',
  value: '',
  ...extra,
})

const labels = { on: '开', off: '关', empty: '（空）' }

describe('splitFieldsByGroup', () => {
  it('后端没给 group 时全部平铺，没有折叠面板', () => {
    const fields = [field('a'), field('b')]
    expect(splitFieldsByGroup(fields)).toEqual({ common: fields, groups: [] })
  })

  it('common 平铺，其余分组按首次出现顺序、组内保持后端顺序', () => {
    const fields = [
      field('team1', { group: 'team' }),
      field('a'),
      field('sup', { group: 'support', overridden: true }),
      field('team2', { group: 'team', overridden: true }),
      field('b', { group: 'common' }),
    ]
    const layout = splitFieldsByGroup(fields)
    expect(layout.common.map(item => item.key)).toEqual(['a', 'b'])
    expect(layout.groups.map(group => [group.key, group.fields.map(item => item.key)])).toEqual([
      ['team', ['team1', 'team2']],
      ['support', ['sup']],
    ])
    expect(layout.groups.map(group => group.overriddenCount)).toEqual([1, 1])
  })

  it('visible_when 不满足时隐藏；整组都隐藏时不出空面板，但仍计入已改数', () => {
    const fields = [
      field('currencyWars.mode', { type: 'select', value: 0 }),
      field('currencyWars.reroll.bossNames', {
        group: 'reroll',
        overridden: true,
        visible_when: { key: 'currencyWars.mode', values: [2] },
      }),
    ]
    expect(splitFieldsByGroup(fields).groups).toEqual([])
    fields[0].value = 2
    const layout = splitFieldsByGroup(fields)
    expect(layout.groups).toHaveLength(1)
    expect(layout.groups[0].overriddenCount).toBe(1)
  })
})

describe('isFieldVisible', () => {
  it('依赖字段不在表单里时照常显示', () => {
    const dependent = field('x', { visible_when: { key: 'missing', values: [true] } })
    expect(isFieldVisible(dependent, [dependent])).toBe(true)
  })

  it('按依赖字段当前值判断', () => {
    const toggle = field('activity.enabled', { type: 'boolean', value: false })
    const dependent = field('activity.level', {
      visible_when: { key: 'activity.enabled', values: [true] },
    })
    expect(isFieldVisible(dependent, [toggle, dependent])).toBe(false)
    toggle.value = true
    expect(isFieldVisible(dependent, [toggle, dependent])).toBe(true)
  })
})

describe('单项恢复与摘要', () => {
  it('只有被覆盖且带 native_value 的字段能单项恢复', () => {
    expect(canResetField(field('a'))).toBe(false)
    expect(canResetField(field('a', { overridden: true }))).toBe(false)
    expect(canResetField(field('a', { overridden: true, native_value: 0 }))).toBe(true)
    expect(canResetField(field('a', { overridden: false, native_value: 0 }))).toBe(false)
  })

  it('值格式化：开关、下拉选项名、空值、长 JSON 截断', () => {
    expect(formatManagedValue(field('a'), true, labels)).toBe('开')
    expect(
      formatManagedValue(
        field('a', { type: 'select', options: [{ value: 2, label: '刷开局' }] }),
        2,
        labels
      )
    ).toBe('刷开局')
    expect(formatManagedValue(field('a'), '', labels)).toBe('（空）')
    expect(formatManagedValue(field('a'), [], labels)).toBe('（空）')
    expect(formatManagedValue(field('a'), 'x'.repeat(80), labels)).toHaveLength(60)
  })

  it('摘要最多列两个改过的设置，没改过返回 null', () => {
    expect(summarizeOverriddenFields([field('a')], labels)).toBeNull()
    const summary = summarizeOverriddenFields(
      [
        field('a', { label: '次数', value: 3, overridden: true }),
        field('b', { label: '秘技', value: false, overridden: true }),
        field('c', { overridden: true }),
      ],
      labels
    )
    expect(summary).toEqual({
      items: [
        { label: '次数', value: '3' },
        { label: '秘技', value: '关' },
      ],
      rest: 1,
    })
  })

  it('培养目标开关只在开启时返回', () => {
    const sra = [field('useBuildTarget', { type: 'boolean', value: true, label: '使用培养目标' })]
    expect(findEnabledBuildTargetField('SRA', sra)?.label).toBe('使用培养目标')
    expect(findEnabledBuildTargetField('M7A', sra)).toBeNull()
    expect(
      findEnabledBuildTargetField('M7A', [
        field('build_target_enable', { type: 'boolean', value: false }),
      ])
    ).toBeNull()
    expect(findEnabledBuildTargetField(undefined, sra)).toBeNull()
  })
})

describe('三月七列表字段的行编辑器', () => {
  it('只有值是数组的两个键才用行编辑器', () => {
    expect(isRowListField(field('instance_teams', { type: 'json', value: [] }))).toBe(true)
    expect(isRowListField(field('borrow_friends', { type: 'json', value: [] }))).toBe(true)
    expect(isRowListField(field('instance_teams', { type: 'json', value: {} }))).toBe(false)
    expect(isRowListField(field('other', { type: 'json', value: [] }))).toBe(false)
  })

  it('instance_teams：数字队伍号读成字符串，写回时丢掉没填完的行、保留未知键', () => {
    const rows = listFieldToRows('instance_teams', [
      { instance_name: '拟造花萼', team_number: 6, note: 'x' },
      null,
      'bad',
    ])
    expect(rows).toEqual([{ first: '拟造花萼', second: '6', rest: { note: 'x' } }])
    expect(
      rowsToListField('instance_teams', [
        ...rows,
        { first: '', second: '1' },
        { first: 'a', second: '' },
      ])
    ).toEqual([{ note: 'x', instance_name: '拟造花萼', team_number: '6' }])
  })

  it('borrow_friends：保留 None 行，丢掉角色名为空的行', () => {
    const rows = listFieldToRows('borrow_friends', [['March7th', '赵相机'], ['None', ''], 'bad'])
    expect(rows).toEqual([
      { first: 'March7th', second: '赵相机' },
      { first: 'None', second: '' },
    ])
    expect(rowsToListField('borrow_friends', [...rows, { first: ' ', second: 'x' }])).toEqual([
      ['March7th', '赵相机'],
      ['None', ''],
    ])
  })
})
