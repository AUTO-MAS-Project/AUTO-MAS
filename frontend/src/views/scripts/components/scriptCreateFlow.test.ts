import { describe, expect, it } from 'vite-plus/test'
import {
  SCRIPT_TYPE_OPTIONS,
  filterScriptTypeOptions,
  splitScriptTypeOptions,
} from './scriptCreateFlow'

describe('script creation choices', () => {
  it('keeps the existing order and the two general choices', () => {
    expect(SCRIPT_TYPE_OPTIONS.map(option => option.value)).toEqual([
      'General',
      'MaaFW',
      'MAA',
      'SRC',
      'MaaEnd',
      'M9A',
      'Okww',
      'OkNte',
      'HSR',
      'BetterGI',
      'ZzzOd',
      'BAAH',
      'Whimbox',
      'MSS',
    ])
    expect(splitScriptTypeOptions(SCRIPT_TYPE_OPTIONS).general.map(option => option.value)).toEqual(
      ['General', 'MaaFW']
    )
  })

  it('finds script families by Chinese aliases and translated descriptions', () => {
    expect(
      filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, '星穹铁道').map(option => option.value)
    ).toEqual(['SRC'])
    expect(
      filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, 'maaframework').map(option => option.value)
    ).toEqual(['MaaFW', 'MaaEnd', 'MSS'])
    expect(
      filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, 'localized source', key =>
        key === 'core.scripts.create.typeDesc.General' ? 'Localized source' : ''
      ).map(option => option.value)
    ).toEqual(['General'])
  })
})
