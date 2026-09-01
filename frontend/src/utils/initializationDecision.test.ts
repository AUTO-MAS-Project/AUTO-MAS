import { describe, expect, it } from 'vitest'
import { decideFailureActions, filterRuntimeMirrors } from './initializationDecision'
import type { FailureActionKind } from './initializationDecision'

const kinds = (context: Parameters<typeof decideFailureActions>[0]): FailureActionKind[] =>
  decideFailureActions(context).actions.map(action => action.kind)

describe('decideFailureActions', () => {
  // 下面几条的 code / retryable / remediation 组合都抄自
  // electron/services/runtime/protocol.ts 的错误码定义表，不是编出来的。
  it('retry 与 retry-sync 都收敛成同一个「重试」', () => {
    expect(kinds({ code: 'DIRECTORY_OCCUPIED', retryable: true, remediation: ['retry'] })).toEqual([
      'retry',
    ])
    expect(
      kinds({
        code: 'GIT_REPOSITORY_INVALID',
        retryable: true,
        remediation: ['retry-sync'],
        stage: 'repository',
      })
    ).toEqual(['retry'])
  })

  it('retry-other-mirror 给出换镜像按钮并展开镜像面板', () => {
    const plan = decideFailureActions({
      code: 'MIRROR_EXHAUSTED',
      retryable: true,
      remediation: ['retry-other-mirror'],
      stage: 'repository',
      runtimeMode: 'managed',
    })

    expect(plan.actions.map(action => action.kind)).toEqual(['retry-other-mirror'])
    expect(plan.actions[0].labelKey).toBe('init.failure.retryOtherMirror')
    expect(plan.showMirrorSelection).toBe(true)
    expect(plan.legacy).toBe(false)
  })

  // 依赖段的包索引被 uv.lock 冻结，Runtime 收不下 package-index 镜像，
  // 给了按钮也只会弹出一个空面板。
  it('Runtime 下依赖段的换镜像降级成普通重试', () => {
    const plan = decideFailureActions({
      code: 'DEPENDENCY_SYNC_FAILED',
      retryable: true,
      remediation: ['retry-other-mirror'],
      stage: 'dependency',
      runtimeMode: 'managed',
    })

    expect(plan.actions.map(action => action.kind)).toEqual(['retry'])
    expect(plan.showMirrorSelection).toBe(false)
  })

  it('rebuild-environment 与 open-log 按 remediation 的顺序排列', () => {
    expect(
      kinds({
        code: 'DEPENDENCY_SYNC_FAILED',
        retryable: true,
        remediation: ['retry-sync', 'rebuild-environment', 'open-log'],
        stage: 'dependency',
        runtimeMode: 'managed',
      })
    ).toEqual(['retry', 'rebuild-environment', 'open-log'])
  })

  it('run-doctor 给出诊断按钮', () => {
    expect(
      kinds({
        code: 'UV_EXEC_FAILED',
        retryable: true,
        remediation: ['run-doctor', 'open-log'],
        stage: 'python',
        runtimeMode: 'managed',
      })
    ).toEqual(['run-doctor', 'open-log'])
  })

  it('contact-support 带出日志按钮与一段提示，可重试时不影响重试', () => {
    const plan = decideFailureActions({
      code: 'UV_CHECKSUM_MISMATCH',
      retryable: true,
      remediation: ['retry-other-mirror', 'contact-support'],
      stage: 'python',
      runtimeMode: 'managed',
    })

    expect(plan.actions.map(action => action.kind)).toEqual(['retry-other-mirror', 'open-log'])
    expect(plan.notice).toBe('contact-support')
  })

  it('INTERNAL_ERROR 只给打开日志，并说明是运行时内部错误', () => {
    const plan = decideFailureActions({
      code: 'INTERNAL_ERROR',
      retryable: false,
      remediation: ['open-log', 'contact-support'],
      stage: 'python',
      runtimeMode: 'managed',
    })

    expect(plan.actions.map(action => action.kind)).toEqual(['open-log'])
    expect(plan.notice).toBe('internal-error')
    expect(plan.showMirrorSelection).toBe(false)
  })

  // Runtime 万一把 INTERNAL_ERROR 标成可重试，界面也不能给重试按钮。
  it('INTERNAL_ERROR 即使被标为可重试也不给重试', () => {
    expect(
      kinds({
        code: 'INTERNAL_ERROR',
        retryable: true,
        remediation: ['retry', 'open-log'],
        runtimeMode: 'managed',
      })
    ).toEqual(['open-log'])
  })

  it('retryable=false 屏蔽全部重试类按钮，只留下非重试动作', () => {
    expect(
      kinds({
        code: 'BACKEND_IDENTITY_MISMATCH',
        retryable: false,
        remediation: ['retry-sync', 'run-doctor', 'open-log'],
        stage: 'backend',
        runtimeMode: 'managed',
      })
    ).toEqual(['run-doctor', 'open-log'])
  })

  it('重试全被屏蔽后至少留一个打开日志', () => {
    const plan = decideFailureActions({
      code: 'PYTHON_VERSION_MISMATCH',
      retryable: false,
      remediation: ['rebuild-environment'],
      stage: 'python',
      runtimeMode: 'managed',
    })

    expect(plan.actions.map(action => action.kind)).toEqual(['open-log'])
    expect(plan.legacy).toBe(false)
  })

  it('旧链路缺字段时保持现有行为：重试加镜像面板', () => {
    const plan = decideFailureActions({ stage: 'python' })

    expect(plan.actions).toEqual([
      { kind: 'retry-other-mirror', labelKey: 'init.step.retryWithMirror' },
    ])
    expect(plan.showMirrorSelection).toBe(true)
    expect(plan.legacy).toBe(true)
    expect(plan.notice).toBeNull()
  })

  it('未知 code 与未知 remediation 都退回现有行为', () => {
    expect(decideFailureActions({ code: 'SOMETHING_NEW', retryable: true }).legacy).toBe(true)
    // update-desktop / select-version 这类动作界面做不了，全都认不出来就当旧链路
    expect(
      decideFailureActions({
        code: 'GIT_BRANCH_NOT_FOUND',
        retryable: true,
        remediation: ['select-version', 'not-a-real-remediation'],
      }).legacy
    ).toBe(true)
  })

  it('认不出来又不可重试时只给日志，不给一个空界面', () => {
    const plan = decideFailureActions({
      code: 'PROTOCOL_MISMATCH',
      retryable: false,
      remediation: ['update-desktop'],
      runtimeMode: 'managed',
    })

    expect(plan.actions.map(action => action.kind)).toEqual(['open-log'])
    expect(plan.notice).toBe('contact-support')
  })

  it('认识的动作留下，不认识的忽略', () => {
    expect(
      kinds({
        code: 'GIT_REPO_CLEANUP_FAILED',
        retryable: true,
        remediation: ['cleanup', 'open-log'],
        stage: 'repository',
        runtimeMode: 'managed',
      })
    ).toEqual(['open-log'])
  })

  it('后端段的 restart-backend 也是重试', () => {
    expect(
      kinds({
        code: 'BACKEND_HEALTH_TIMEOUT',
        retryable: true,
        remediation: ['restart-backend', 'open-log'],
        stage: 'backend',
        runtimeMode: 'managed',
      })
    ).toEqual(['retry', 'open-log'])
  })

  it('同一个动作出现两次只给一个按钮', () => {
    expect(
      kinds({
        code: 'DEPENDENCY_SYNC_FAILED',
        retryable: true,
        remediation: ['retry', 'retry-sync', 'open-log'],
        stage: 'dependency',
        runtimeMode: 'managed',
      })
    ).toEqual(['retry', 'open-log'])
  })
})

describe('filterRuntimeMirrors', () => {
  const mirrors = [{ key: 'cnb' }, { key: 'github' }, { key: '阿里云' }]
  const mirrorKeys = { python: ['official'], repository: ['cnb', 'github'], dependency: [] }

  it('旧链路原样返回', () => {
    expect(filterRuntimeMirrors(mirrors, 'repository', 'off', mirrorKeys)).toEqual(mirrors)
    expect(filterRuntimeMirrors(mirrors, 'repository', undefined, undefined)).toEqual(mirrors)
  })

  it('Runtime 下只留映射得到的镜像键', () => {
    expect(filterRuntimeMirrors(mirrors, 'repository', 'managed', mirrorKeys)).toEqual([
      { key: 'cnb' },
      { key: 'github' },
    ])
  })

  it('Runtime 下依赖段与未知段一个都不展示', () => {
    expect(filterRuntimeMirrors(mirrors, 'dependency', 'managed', mirrorKeys)).toEqual([])
    expect(filterRuntimeMirrors(mirrors, 'pip', 'managed', mirrorKeys)).toEqual([])
  })
})
