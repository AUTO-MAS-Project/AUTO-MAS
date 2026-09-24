import { describe, expect, it } from 'vitest'
import { normalizeMaaFWProjectName, resolveMaaFWProjectName } from './maafwProjectName'

// 样本照抄真实项目经后端预览接口返回的 project.name / label / title
// （没写 label 的项目，后端会把 label 补成 name；没写 title 的拼成「label 版本」）
describe('resolveMaaFWProjectName', () => {
  it.each([
    [
      '没写 label，title 带版本号与标语',
      {
        name: 'MAA_bbb',
        label: 'MAA_bbb',
        title: '识宝小助手 Oᴗoಣ | 版本号:v1.13.3 | 自动乐土激情开发中',
      },
      '识宝小助手 Oᴗoಣ',
    ],
    [
      '没写 label，title 不带版本',
      { name: 'MaaStarResonance', label: 'MaaStarResonance', title: '星痕共鸣MAA小助手' },
      '星痕共鸣MAA小助手',
    ],
    [
      'title 首段是「名字 版本」',
      { name: 'MRA', label: 'MRA', title: 'MRA v3.2.0 | 舰R小助手' },
      'MRA',
    ],
    [
      '写了 label 就用 label',
      { name: 'MaaTOT', label: '生煎包小助手', title: 'MaaTOT v5.2.8 | 生煎包小助手' },
      '生煎包小助手',
    ],
    ['label 只改大小写也算写了', { name: 'm9a', label: 'M9A', title: 'M9A v4.9.0' }, 'M9A'],
    [
      '都没写：title 是拼出来的「label 版本」',
      { name: 'MaaEnd', label: 'MaaEnd', title: 'MaaEnd v2.29.0' },
      'MaaEnd',
    ],
  ])('%s', (_case, project, expected) => {
    expect(resolveMaaFWProjectName(project)).toBe(expected)
  })

  it('翻不出来的 i18n 键不算名字，什么都没有时给空串由调用方兜底', () => {
    expect(
      resolveMaaFWProjectName({ name: 'X', label: '$project_label', title: '$project_title' })
    ).toBe('X')
    expect(resolveMaaFWProjectName(null)).toBe('')
  })
})

describe('normalizeMaaFWProjectName', () => {
  it('全角竖线同样分段，带预发布后缀的版本号也去掉', () => {
    expect(normalizeMaaFWProjectName('某助手 v1.0.0-beta.2｜标语')).toBe('某助手')
  })
})
