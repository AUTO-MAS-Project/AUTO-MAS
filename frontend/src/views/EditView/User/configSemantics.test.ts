import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'
import zhCN from '../../../i18n/locales/zh-CN'
import { composeConfigSemantics, type Translate } from './configSemantics'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})
const t = i18n.global.t as unknown as Translate

const kindOf = {
  shared: { off: ['shared', false], on: ['shared', true] },
  independent: { off: ['independent', false], on: ['independent', true] },
  native: { off: ['native', false], on: ['native', true] },
} as const

describe('base ⊕ overlay 生效语义', () => {
  // 六个子态各给一条完整说明：配置归谁、任务期间怎么用、结束会不会留下改动。
  it('六个子态的标题逐字点明用的哪份配置、有没有覆写', () => {
    expect(composeConfigSemantics('shared', false, t).formula).toBe('直接使用共享基础配置')
    expect(composeConfigSemantics('shared', true, t).formula).toBe('共享基础配置 + 本账号的覆写')
    expect(composeConfigSemantics('independent', false, t).formula).toBe('直接使用独立基础配置')
    expect(composeConfigSemantics('independent', true, t).formula).toBe(
      '独立基础配置 + 本账号的覆写'
    )
    expect(composeConfigSemantics('native', false, t).formula).toBe('直接使用外部脚本的原生配置')
    expect(composeConfigSemantics('native', true, t).formula).toBe('用本页字段覆写脚本自带的配置')
  })

  it('overlay 未启用：说明这份基础配置不会被 MAS 改动', () => {
    for (const kind of ['shared', 'independent', 'native'] as const) {
      const [base, quick] = kindOf[kind].off
      const { note } = composeConfigSemantics(base, quick, t)
      expect(note).toContain('任务')
      expect(note).toContain('不会改动')
    }
  })

  it('overlay 启用：说明任务期间临时覆写、结束恢复、不污染原配置', () => {
    for (const kind of ['shared', 'independent', 'native'] as const) {
      const [base, quick] = kindOf[kind].on
      const { note } = composeConfigSemantics(base, quick, t)
      expect(note).toContain('任务运行期间')
      expect(note).toContain('任务结束（含失败、取消、异常）')
      expect(note).toContain('恢复')
      expect(note).toContain('不会污染')
    }
  })

  it('改动范围一句话点明这次任务改的是哪一份配置，六个子态各不相同', () => {
    const effects = (['shared', 'independent', 'native'] as const).flatMap(kind =>
      (['off', 'on'] as const).map(state => {
        const [base, quick] = kindOf[kind][state]
        const { effect } = composeConfigSemantics(base, quick, t)
        if (state === 'off') {
          expect(effect).toMatch(/^不改动/)
        } else {
          expect(effect).toContain('临时覆写')
          expect(effect).toContain('任务结束自动恢复')
        }
        return effect
      })
    )
    expect(new Set(effects).size).toBe(6)
    // 目标沿用「配置操作」块的落点说法，两处指的是同一个东西
    expect(effects[0]).toBe('不改动这份共享基础配置')
    expect(effects[1]).toBe('临时覆写这份共享基础配置，任务结束自动恢复')
    expect(effects[4]).toBe('不改动脚本自带的原生配置')
  })

  it('说明不是「A + B」式短语拼接，每个子态都有独立的一段解释', () => {
    const notes = (['shared', 'independent', 'native'] as const).flatMap(kind =>
      (['off', 'on'] as const).map(state => {
        const [base, quick] = kindOf[kind][state]
        return composeConfigSemantics(base, quick, t).note
      })
    )
    expect(new Set(notes).size).toBe(6)
    for (const note of notes) expect(note.length).toBeGreaterThan(30)
  })

  it('未接入 overlay 的专项不渲染语义：没有覆写层就没有子态可讲', () => {
    // General / HSR / BAAH / ZzzOd 没有覆写层，且本身就是 MAS 在写配置，
    // off 文案里的「不覆写常规配置时 MAS 仅启动脚本」对它们不成立。
    for (const base of ['shared', 'independent', 'native'] as const) {
      expect(composeConfigSemantics(base, undefined, t)).toEqual({
        formula: '',
        effect: '',
        note: '',
        gui: '',
      })
    }
  })

  it('默认两态卡片的布尔取值映射到独立 / 原生', () => {
    expect(composeConfigSemantics(true, false, t).formula).toBe('直接使用独立基础配置')
    expect(composeConfigSemantics(false, true, t).formula).toBe('用本页字段覆写脚本自带的配置')
  })

  it('界面入口说明随 base 来源变化：打开脚本自带界面改的是哪一份配置', () => {
    const guis = (['shared', 'independent', 'native'] as const).map(kind => {
      const [base, quick] = kindOf[kind].off
      const gui = composeConfigSemantics(base, quick, t).gui
      expect(gui).toContain('打开脚本自带界面')
      // 界面入口只随 base 来源变化，与有没有覆盖层无关
      const [onBase, onQuick] = kindOf[kind].on
      expect(composeConfigSemantics(onBase, onQuick, t).gui).toBe(gui)
      return gui
    })
    expect(new Set(guis).size).toBe(3)
    expect(guis[0]).toContain('所有账号共用')
    expect(guis[1]).toContain('其他账号不受影响')
    expect(guis[2]).toContain('MAS 不接管')
  })

  it('未知 base 值不渲染语义', () => {
    expect(composeConfigSemantics('', true, t)).toEqual({
      formula: '',
      effect: '',
      note: '',
      gui: '',
    })
  })
})
