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
  shared: { off: ['脚本', false], on: ['脚本', true] },
  independent: { off: ['用户', false], on: ['用户', true] },
  native: { off: ['直控', false], on: ['直控', true] },
} as const

describe('base ⊕ overlay 生效语义', () => {
  // 六个子态各给一条完整说明：配置归谁、任务期间怎么用、结束会不会留下改动。
  it('六个子态的标题逐字点明用的哪份配置、有没有覆写', () => {
    expect(composeConfigSemantics('脚本', false, t).formula).toBe('直接使用共享基础配置')
    expect(composeConfigSemantics('脚本', true, t).formula).toBe('共享基础配置 + 本账号的覆写')
    expect(composeConfigSemantics('用户', false, t).formula).toBe('直接使用独立基础配置')
    expect(composeConfigSemantics('用户', true, t).formula).toBe('独立基础配置 + 本账号的覆写')
    expect(composeConfigSemantics('直控', false, t).formula).toBe('直接使用外部脚本的原生配置')
    expect(composeConfigSemantics('直控', true, t).formula).toBe('用本页字段覆写脚本自带的配置')
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
    for (const base of ['脚本', '用户', '直控'] as const) {
      expect(composeConfigSemantics(base, undefined, t)).toEqual({
        formula: '',
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
    expect(composeConfigSemantics('', true, t)).toEqual({ formula: '', note: '', gui: '' })
  })
})
