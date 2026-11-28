import { describe, expect, it } from 'vite-plus/test'
import type { PluginCatalogGetOut } from '@/api'
import { toMarketViews, updatableEntries, type PluginModelContext } from '../pluginCenterModel'
import type { InstallTask } from '../usePluginInstallation'
import {
  batchUpdateState,
  restartTask,
  showsUpdateButton,
  updatePhaseStatus,
  upToDateCount,
} from './updatesModel'

const context: PluginModelContext = {
  bindings: [],
  appIcon: '',
  texts: { text: () => undefined, tags: () => undefined },
}
const install = (editable: boolean) => ({ hints: { info: [{ field: 'install', editable }] } })
const catalog = (records: Record<string, { info: object; ui?: object }>): PluginCatalogGetOut => ({
  order: Object.keys(records).map(uid => ({ uid, type: 'PluginMeta' })),
  data: Object.fromEntries(
    Object.entries(records).map(([uid, value]) => [uid, { uid, ui: value.ui ?? {}, ...value }])
  ),
})
const outdated = (id: string) => ({
  plugin_name: id,
  version: '2.0',
  installed_version: '1.0',
  update_available: true,
})
const task = (phase: InstallTask['phase']): InstallTask => ({
  uid: 'a',
  pluginId: 'a',
  upgrade: true,
  phase,
})

describe('更新页签', () => {
  const market = toMarketViews(
    catalog({
      a: { info: outdated('a'), ui: install(true) },
      latest: { info: { plugin_name: 'latest', version: '1.0', installed_version: '1.0' } },
      b: { info: outdated('b'), ui: install(false) },
      hidden: { info: outdated('hidden') },
      c: { info: outdated('c'), ui: install(true) },
      notInstalled: { info: { plugin_name: 'n', version: '1.0' } },
    }),
    null,
    context
  )
  const updates = updatableEntries(market, [])

  it('「全部更新」按目录顺序排队界面提示里有安装操作的条目，至少两项才出现', () => {
    const state = batchUpdateState(updates)
    expect(state.targets.map(entry => entry.uid)).toEqual(['a', 'b', 'c'])
    expect(state).toMatchObject({ visible: true, editable: true })
    expect(batchUpdateState(updates.filter(item => item.entry.uid === 'a')).visible).toBe(false)
    expect(batchUpdateState(updates.filter(item => item.entry.uid === 'b')).editable).toBe(false)
  })

  it('行内按钮：排队、进行中只显示阶段；没有任务、失败、完成后仍可更新时给按钮', () => {
    const [a] = updates.map(item => item.entry)
    expect(showsUpdateButton(a, null)).toBe(true)
    expect(showsUpdateButton(a, task('failed'))).toBe(true)
    for (const phase of ['queued', 'running', 'waiting'] as const)
      expect(showsUpdateButton(a, task(phase))).toBe(false)
    // 本次已更新成功、后端仍报可更新（又出了新版本）时要能再点。
    expect(showsUpdateButton(a, task('succeeded'))).toBe(true)
    const hidden = updates.find(item => item.entry.uid === 'hidden')!.entry
    expect(showsUpdateButton(hidden, null)).toBe(false)
  })

  it('阶段标签与重启提示只在对应阶段出现', () => {
    expect(updatePhaseStatus(null)).toBeNull()
    expect(updatePhaseStatus(task('running'))).toMatchObject({
      labelKey: 'core.plugins.installPhase.upgrading',
      tone: 'processing',
    })
    expect(updatePhaseStatus(task('failed'))?.tone).toBe('error')
    // 完成后还留在列表里的行只给按钮，不同时挂「已完成」。
    expect(updatePhaseStatus(task('succeeded'))).toBeNull()
    expect(restartTask(task('running'))).toBeNull()
    expect(restartTask(null)).toBeNull()
    for (const phase of ['waiting', 'restarting', 'recovering'] as const)
      expect(restartTask(task(phase))?.phase).toBe(phase)
  })

  it('「其余已是最新」只数已安装且无更新的条目', () => {
    expect(upToDateCount(market)).toBe(1)
    expect(upToDateCount([])).toBe(0)
  })
})
