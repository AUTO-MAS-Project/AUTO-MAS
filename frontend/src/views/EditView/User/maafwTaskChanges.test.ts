import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '@/i18n'
import type { MaaFWOptionInfo } from '@/types/script'
import {
  describeMaaFWMissingTaskSettings,
  maafwMissingTaskName,
  markMaaFWTasksSeen,
  resolveMaaFWNewTaskNames,
} from './maafwTaskChanges'

const option = (partial: Partial<MaaFWOptionInfo> & { name: string }): MaaFWOptionInfo => ({
  type: 'select',
  controller: [],
  resource: [],
  cases: [],
  inputs: [],
  hotkeys: [],
  ...partial,
})

describe('maafwMissingTaskName', () => {
  it('副本 id 去掉后缀，首份原样', () => {
    expect(maafwMissingTaskName('StartUp')).toBe('StartUp')
    expect(maafwMissingTaskName('StartUp__MAS_DUP__x1')).toBe('StartUp')
  })
})

describe('describeMaaFWMissingTaskSettings', () => {
  const options = [
    option({
      name: 'Difficulty',
      label: '难度',
      cases: [
        { name: 'Hard', label: '困难', option: [] },
        { name: 'Normal', label: '普通', option: [] },
      ],
    }),
    option({
      name: 'Stages',
      label: '关卡',
      type: 'checkbox',
      cases: [
        { name: 'A', label: '甲', option: [] },
        { name: 'B', label: '乙', option: [] },
      ],
    }),
    option({
      name: 'Login',
      label: '登录',
      type: 'input',
      inputs: [
        { name: 'User', label: '账号' },
        { name: 'Pass', label: '密码', password: true },
      ],
    }),
    option({ name: 'Nick', label: '昵称', type: 'input', inputs: [{ name: 'Nick' }] }),
  ]

  it('选项还在时用显示名与 case 显示名', () => {
    expect(
      describeMaaFWMissingTaskSettings(
        { Difficulty: 'Hard', Stages: ['A', 'B'], Nick: { Nick: '小明' } },
        options
      )
    ).toEqual([
      { key: 'Difficulty', label: '难度', value: '困难' },
      { key: 'Stages', label: '关卡', value: '甲、乙' },
      { key: 'Nick', label: '昵称', value: '小明' },
    ])
  })

  it('密码字段与密文一律打码', () => {
    const rows = describeMaaFWMissingTaskSettings(
      { Login: { User: 'me', Pass: 'mas-dpapi:abc' }, Gone: 'mas-dpapi:xyz' },
      options
    )
    expect(rows).toEqual([
      { key: 'Login', label: '登录', value: '账号: me，密码: ******' },
      { key: 'Gone', label: 'Gone', value: '******' },
    ])
  })

  it('选项已不在 interface 里时原样给键和值', () => {
    expect(describeMaaFWMissingTaskSettings({ Old: 'X', OldList: ['p', 'q'] }, [])).toEqual([
      { key: 'Old', label: 'Old', value: 'X' },
      { key: 'OldList', label: 'OldList', value: 'p、q' },
    ])
  })

  it('按 interface 里选项的顺序排，已不在的排后面', () => {
    const rows = describeMaaFWMissingTaskSettings(
      { Gone: 'X', Nick: { Nick: 'n' }, Difficulty: 'Normal' },
      options
    )
    expect(rows.map(row => row.key)).toEqual(['Difficulty', 'Nick', 'Gone'])
  })

  it('分隔符跟界面语言走', () => {
    i18n.global.locale.value = 'en-US'
    try {
      const rows = describeMaaFWMissingTaskSettings(
        { Stages: ['A', 'B'], Login: { User: 'me', Pass: 'x' } },
        options
      )
      expect(rows.map(row => row.value)).toEqual(['甲, 乙', '账号: me; 密码: ******'])
    } finally {
      i18n.global.locale.value = 'zh-CN'
    }
  })

  it('没有设置时为空', () => {
    expect(describeMaaFWMissingTaskSettings(undefined, options)).toEqual([])
  })
})

describe('NEW 标记的已见任务', () => {
  let store: Map<string, string>

  beforeEach(() => {
    store = new Map()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('第一次打开把现有任务全记成见过，不标 NEW', () => {
    expect(resolveMaaFWNewTaskNames('s1', ['A', 'B'])).toEqual(new Set())
    expect(JSON.parse(store.get('maafw-seen-tasks:s1') || '[]')).toEqual(['A', 'B'])
  })

  it('之后多出来的任务标 NEW，加进队列后消掉', () => {
    resolveMaaFWNewTaskNames('s1', ['A', 'StartUp'])
    // 项目更新把 StartUp 改名成 LaunchGame
    expect(resolveMaaFWNewTaskNames('s1', ['A', 'LaunchGame'])).toEqual(new Set(['LaunchGame']))
    markMaaFWTasksSeen('s1', ['LaunchGame'])
    expect(resolveMaaFWNewTaskNames('s1', ['A', 'LaunchGame'])).toEqual(new Set())
  })

  it('按脚本分开记', () => {
    resolveMaaFWNewTaskNames('s1', ['A'])
    expect(resolveMaaFWNewTaskNames('s2', ['A', 'B'])).toEqual(new Set())
    expect(resolveMaaFWNewTaskNames('s1', ['A', 'B'])).toEqual(new Set(['B']))
  })

  it('存储不可用时不报错，也不标 NEW', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
    })
    expect(resolveMaaFWNewTaskNames('s1', ['A'])).toEqual(new Set())
    expect(() => markMaaFWTasksSeen('s1', ['A'])).not.toThrow()
  })
})
