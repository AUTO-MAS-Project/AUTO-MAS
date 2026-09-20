import { describe, expect, it } from 'vitest'
import { centerIconUrl, satelliteModules } from './satellite-config'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'
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
