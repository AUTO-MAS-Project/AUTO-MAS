import { describe, expect, it } from 'vitest'
import { fromBackendSettings, toBackendPatch } from './settings'

describe('settings wire adapter', () => {
  it('maps new setting groups and acronym fields to the legacy view model', () => {
    const view = fromBackendSettings({
      appearance: { if_show_tray: true },
      notify: {
        if_openclaw_qq: true,
        openclaw_qq_app_id: 'app-id',
        openclaw_qq_target_open_id: 'target-id',
      },
      updates: { pause_until: '2030-01-02' },
    })

    expect(view.UI?.IfShowTray).toBe(true)
    expect(view.Notify?.IfOpenClawQQ).toBe(true)
    expect(view.Notify?.OpenClawQQAppId).toBe('app-id')
    expect(view.Notify?.OpenClawQQTargetOpenId).toBe('target-id')
    expect(view.Update?.PauseUntil).toBe('2030-01-02')
  })

  it('uses the backend updates group for update setting patches', () => {
    expect(toBackendPatch('Update', { IfAutoUpdate: true, PauseUntil: '2030-01-02' })).toEqual({
      updates: { if_auto_update: true, pause_until: '2030-01-02' },
    })
  })

  it('maps the notification trigger through the new config update contract', () => {
    expect(toBackendPatch('Notify', { Test: true })).toEqual({
      notify: { test: true },
    })
  })
})
