import { describe, expect, it } from 'vitest'
import {
  buildInstalledState,
  buildInstalledVersionMap,
  filterMarketItems,
  isSameVersion,
  mergeInstalledVersions,
  normalizePackageName,
  type MarketItem,
} from './marketModel'

const items: MarketItem[] = [
  {
    package: 'automas_plugin_alpha',
    version: '2.0.0',
    summary: 'Alpha helper',
    project_url: 'https://pypi.org/project/automas-plugin-alpha/',
    prefix_tag: 'automas_plugin_',
  },
  {
    package: 'automas_beta',
    version: '1.0.0',
    summary: 'Beta helper',
    project_url: 'https://pypi.org/project/automas-beta/',
    prefix_tag: 'automas_',
  },
]

describe('plugin market model', () => {
  it('normalizes PyPI equivalent package names', () => {
    expect(normalizePackageName(' AutoMAS-Plugin-Alpha ')).toBe('automas_plugin_alpha')
  })

  it('accepts the current boolean installed map and future version-bearing shapes', () => {
    expect(
      buildInstalledState({
        'automas-plugin-alpha': true,
        automas_beta: { installed: true, version: '0.9.0' },
        automas_gamma: '3.1.4',
      })
    ).toEqual({
      automas_plugin_alpha: { installed: true, version: '' },
      automas_beta: { installed: true, version: '0.9.0' },
      automas_gamma: { installed: true, version: '3.1.4' },
    })
  })

  it('builds a distribution version map from plugin gateway plugin_packages', () => {
    // plugin_packages 以 plugin 名为键；value.package 为 distribution 名（可能带 - 或大小写）
    expect(
      buildInstalledVersionMap({
        alpha: { package: 'AutoMAS-Plugin-Alpha', version: '1.2.3' },
        beta: { package: 'automas_beta', version: null },
        gamma: { package: '', version: '9.9.9' },
        delta: { package: 'automas_delta', version: '  2.0.0  ' },
      })
    ).toEqual({
      automas_plugin_alpha: '1.2.3',
      automas_delta: '2.0.0',
    })
  })

  it('merges gateway versions only into installed entries missing a version', () => {
    const state = {
      automas_plugin_alpha: { installed: true, version: '' },
      automas_beta: { installed: true, version: '0.9.0' },
      automas_gamma: { installed: false, version: '' },
    }
    const merged = mergeInstalledVersions(state, {
      automas_plugin_alpha: '1.2.3',
      automas_beta: '9.9.9',
      automas_gamma: '3.0.0',
    })

    expect(merged).toEqual({
      automas_plugin_alpha: { installed: true, version: '1.2.3' },
      // 快照已带版本时以快照为准
      automas_beta: { installed: true, version: '0.9.0' },
      // 未安装条目不补版本
      automas_gamma: { installed: false, version: '' },
    })
    // 不修改原对象
    expect(state.automas_plugin_alpha.version).toBe('')
  })

  it('compares local and latest versions ignoring blank values and v prefixes', () => {
    expect(isSameVersion('1.2.3', '1.2.3')).toBe(true)
    expect(isSameVersion('v1.2.3', '1.2.3')).toBe(true)
    expect(isSameVersion(' 1.2.3 ', '1.2.3')).toBe(true)
    expect(isSameVersion('1.2.3', '1.2.4')).toBe(false)
    // 版本未上报时不能误判为已是最新
    expect(isSameVersion('', '1.2.3')).toBe(false)
    expect(isSameVersion('', '')).toBe(false)
  })

  it('filters by search, install state and repository prefix without mutating source items', () => {
    const installed = buildInstalledState({ automas_plugin_alpha: true, automas_beta: false })

    expect(filterMarketItems(items, installed, 'alpha', 'all', '')).toEqual([items[0]])
    expect(filterMarketItems(items, installed, '', 'installed', '')).toEqual([items[0]])
    expect(filterMarketItems(items, installed, '', 'available', '')).toEqual([items[1]])
    expect(filterMarketItems(items, installed, '', 'all', 'automas_')).toEqual([items[1]])
    expect(items).toHaveLength(2)
  })
})
