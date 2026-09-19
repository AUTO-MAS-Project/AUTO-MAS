import { describe, expect, it } from 'vitest'

import { buildCreateRequest, buildCreateSteps, isMfwFamily } from './scriptCreateFlow'

/**
 * MFW 家族（MaaFW / M9A）新建时多一步「项目从哪来」：选目录走原来的引导页，
 * 复用已有脚本的项目则建好后直接从那个脚本的副本克隆。这里钉住步骤与请求形状。
 */
describe('scriptCreateFlow · MFW 家族', () => {
  it('MaaFW 与 M9A 都有第二步，其余专项没有', () => {
    expect(isMfwFamily('MaaFW') && isMfwFamily('M9A')).toBe(true)
    expect(isMfwFamily('MaaEnd')).toBe(false)
    expect(buildCreateSteps({ type: 'MaaFW' }).map(step => step.key)).toEqual(['type', 'config'])
    expect(buildCreateSteps({ type: 'M9A' }).map(step => step.titleKey)).toEqual([
      'scripts.create.step.type',
      'scripts.create.step.mfwSource',
    ])
    expect(buildCreateSteps({ type: 'MAA' }).map(step => step.key)).toEqual(['type'])
  })

  it('选目录 → 普通新建；复用 → 带源脚本 id；复用但没选源 → 不提交', () => {
    const base = { configMode: 'template' as const, template: null }
    expect(buildCreateRequest({ ...base, type: 'MaaFW', mfwSourceMode: 'new' })).toEqual({
      kind: 'new',
      type: 'MaaFW',
    })
    expect(
      buildCreateRequest({
        ...base,
        type: 'M9A',
        mfwSourceMode: 'reuse',
        mfwSourceScriptId: 'src-1',
      })
    ).toEqual({ kind: 'mfw-reuse', type: 'M9A', sourceScriptId: 'src-1' })
    expect(
      buildCreateRequest({
        ...base,
        type: 'MaaFW',
        mfwSourceMode: 'reuse',
        mfwSourceScriptId: null,
      })
    ).toBeNull()
    // 复用模式只对 MFW 家族有意义，别的类型照旧
    expect(
      buildCreateRequest({ ...base, type: 'MAA', mfwSourceMode: 'reuse', mfwSourceScriptId: 'x' })
    ).toEqual({ kind: 'new', type: 'MAA' })
  })
})
