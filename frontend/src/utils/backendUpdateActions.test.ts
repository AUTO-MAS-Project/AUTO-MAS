import { describe, expect, it } from 'vitest'

import { resolveBackendUpdateActions } from './backendUpdateActions'

describe('后端更新失败结局到界面动作', () => {
  it('没有结局或已成功时什么按钮都不给', () => {
    expect(resolveBackendUpdateActions(null)).toEqual({
      retryActions: [],
      showRestartBackend: false,
      showContactSupport: false,
    })
    expect(resolveBackendUpdateActions({ success: true })).toEqual({
      retryActions: [],
      showRestartBackend: false,
      showContactSupport: false,
    })
  })

  it('可重试的 bootstrap 失败：按主进程给的顺序展示重试入口', () => {
    expect(
      resolveBackendUpdateActions({
        success: false,
        phase: 'bootstrap',
        code: 'DEPENDENCY_SYNC_FAILED',
        retryable: true,
        retryActions: ['dependencies-sync', 'dependencies-rebuild', 'repair'],
        supportRequired: false,
      })
    ).toEqual({
      retryActions: ['dependencies-sync', 'dependencies-rebuild', 'repair'],
      showRestartBackend: false,
      showContactSupport: false,
    })
  })

  it('不可重试（supportRequired）时一个重试按钮都不给，改为提示反馈', () => {
    // 即便主进程漏了清空 retryActions，渲染侧也要收口。
    expect(
      resolveBackendUpdateActions({
        success: false,
        phase: 'bootstrap',
        code: 'INTERNAL_ERROR',
        retryable: true,
        retryActions: ['repair'],
        supportRequired: true,
      })
    ).toEqual({
      retryActions: [],
      showRestartBackend: false,
      showContactSupport: true,
    })
  })

  it('取消后旧后端拉不起来：结局是 restart，给「重新启动后端」', () => {
    expect(
      resolveBackendUpdateActions({
        success: false,
        phase: 'restart',
        cancelled: true,
        error: '端口被占用',
      })
    ).toEqual({
      retryActions: [],
      showRestartBackend: true,
      showContactSupport: false,
    })
  })

  it('取消且旧后端已拉回来：shutdown 结局没有任何动作按钮', () => {
    expect(
      resolveBackendUpdateActions({
        success: false,
        phase: 'shutdown',
        cancelled: true,
        code: 'OPERATION_CANCELLED',
      })
    ).toEqual({
      retryActions: [],
      showRestartBackend: false,
      showContactSupport: false,
    })
  })
})
