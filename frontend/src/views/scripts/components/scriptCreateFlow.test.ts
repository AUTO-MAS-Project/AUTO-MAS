import { describe, expect, it } from 'vite-plus/test'
import { SCRIPT_TYPE_OPTIONS, filterScriptTypeOptions } from './scriptCreateFlow'

describe('script creation choices', () => {
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
