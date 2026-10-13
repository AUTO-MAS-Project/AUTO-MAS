import { describe, expect, it } from 'vitest'
import {
  buildOrbitModules,
  centerIconUrl,
  orbitKeysByScriptId,
  satelliteModules,
} from './satellite-config'
import { SCRIPT_LABELS, SCRIPT_LOGOS } from '@/utils/scriptLogos'
import type { ScriptType } from '@/types/script'

/**
 * 主页卫星历史上漏过三次（HSR、OK-NTE 由 4fb31ef5 事后补，MaaFW 由 a5cfad20 事后补），
 * 原因是这里维护了一份和 SCRIPT_LOGOS 平行的脚本类型清单，少一个不会报错。现在图标统一
 * 从 SCRIPT_LOGOS 取，这些用例负责钉住「除显式排除的以外，每个脚本类型都有卫星」。
 */
const EXPECTED_EXCLUSIONS: readonly ScriptType[] = ['General']

describe('satellite icon config', () => {
  it('中心图标可用', () => {
    expect(centerIconUrl).not.toBe('')
  })

  it('除显式排除的以外，每个脚本类型都有一颗卫星', () => {
    const allTypes = Object.keys(SCRIPT_LOGOS) as ScriptType[]
    const expected = allTypes.filter(type => !EXPECTED_EXCLUSIONS.includes(type))
    const actual = satelliteModules.map(module => module.scriptType)

    expect([...actual].sort()).toEqual([...expected].sort())
  })

  it('每颗卫星都有非空图标', () => {
    for (const module of satelliteModules) {
      expect(module.iconUrl, `${module.scriptType} 缺少图标`).not.toBe('')
    }
  })

  it('通用脚本不上轨道，因为它的图标就是中心图标', () => {
    expect(satelliteModules.some(module => module.scriptType === 'General')).toBe(false)
    expect(SCRIPT_LOGOS.General).toBe(centerIconUrl)
  })

  it('MAA 排在第一位，未列入顺序表的类型排在后面', () => {
    expect(satelliteModules[0]?.scriptType).toBe('MAA')
  })
})

describe('buildOrbitModules', () => {
  const mfw = (uid: string, info: Record<string, string>) => ({
    uid,
    type: 'MaaFW',
    config: { Info: info },
  })

  it('只有建过的脚本类型上轨道，同类型多个脚本只出一颗', () => {
    const modules = buildOrbitModules([
      { uid: 'h1', type: 'HSR' },
      { uid: 'm1', type: 'MAA' },
      { uid: 'm2', type: 'MAA' },
      { uid: 'g1', type: 'General' },
    ])
    expect(modules.map(module => [module.key, module.scriptIds])).toEqual([
      ['MAA', ['m1', 'm2']],
      ['HSR', ['h1']],
    ])
    expect(modules[0].iconUrl).toBe(SCRIPT_LOGOS.MAA)
    expect(modules[0].fallbackIconUrl).toBeUndefined()
  })

  it('通用 MFW 每个项目一颗，用项目图标、回退 MaaFW 图标；特调还是按类型', () => {
    const modules = buildOrbitModules([
      mfw('a1', { ProjectLabel: '识宝', Path: 'D:/a', Name: '识宝 1' }),
      { uid: 'k1', type: 'M9A' },
      mfw('b1', { ProjectLabel: 'CFA', Path: 'D:/b' }),
      mfw('a2', { ProjectLabel: ' 识宝 ', Path: 'D:/a2', Name: '识宝 2' }),
      mfw('p1', { Path: 'D:/p', Name: '没记项目名' }),
      mfw('p2', { Path: 'D:/p' }),
      mfw('x1', {}),
    ])

    const maafw = modules.filter(module => module.scriptType === 'MaaFW')
    expect(maafw.map(module => [module.key, module.label, module.scriptIds])).toEqual([
      ['MaaFW:project:识宝', '识宝', ['a1', 'a2']],
      ['MaaFW:project:CFA', 'CFA', ['b1']],
      ['MaaFW:path:D:/p', '没记项目名', ['p1', 'p2']],
      ['MaaFW:id:x1', SCRIPT_LABELS.MaaFW, ['x1']],
    ])
    expect(maafw[0].iconUrl).toContain('/api/scripts/maafw/icon?scriptId=a1')
    expect(maafw[0].fallbackIconUrl).toBe(SCRIPT_LOGOS.MaaFW)
    expect(modules.find(module => module.scriptType === 'M9A')).toMatchObject({
      key: 'M9A',
      iconUrl: SCRIPT_LOGOS.M9A,
    })
  })

  it('脚本 ID 对到各自的卫星键', () => {
    const keys = orbitKeysByScriptId(
      buildOrbitModules([
        mfw('a1', { ProjectLabel: '识宝' }),
        mfw('a2', { ProjectLabel: '识宝' }),
        { uid: 'm1', type: 'MAA' },
      ])
    )
    expect([...keys]).toEqual([
      ['m1', 'MAA'],
      ['a1', 'MaaFW:project:识宝'],
      ['a2', 'MaaFW:project:识宝'],
    ])
  })
})
