import { describe, expect, it } from 'vitest'

import { getScriptEditPath, getUserCreatePath, getUserEditPath } from './scriptRegistry'

describe('scriptRegistry routes', () => {
  it.each([
    ['builtin:maa', 'MAA', 'maa'],
    ['builtin:src', 'SRC', 'src'],
    ['builtin:maaend', 'MaaEnd', 'maaend'],
    ['builtin:m9a', 'M9A', 'm9a'],
    ['builtin:maafw', 'MaaFW', 'maafw'],
    ['builtin:ok-script', 'OkScript', 'ok-script'],
    ['plugin:automas_script_hsr', 'HSR', 'hsr'],
  ])('maps %s records to the %s editor route', (editorKind, type, segment) => {
    expect(getScriptEditPath({ id: 'script-id', type, editorKind })).toBe(
      `/scripts/script-id/edit/${segment}`
    )
  })

  it('keeps legacy type-key routes when editor metadata is unavailable', () => {
    expect(getScriptEditPath({ id: 'm9a-id', type: 'M9A' })).toBe('/scripts/m9a-id/edit/maafw')
    expect(getScriptEditPath({ id: 'okww-id', type: 'Okww' })).toBe('/scripts/okww-id/edit/okww')
  })

  it('uses plugin and schema fallbacks for extensible script types', () => {
    expect(
      getScriptEditPath({ id: 'plugin-id', type: 'PluginScript', editorKind: 'plugin:example' })
    ).toBe('/scripts/plugin-id/edit/plugin')
    expect(getScriptEditPath({ id: 'schema-id', type: 'SchemaScript' })).toBe(
      '/scripts/schema-id/edit/schema'
    )
  })

  it('uses the same route segment for user creation and editing', () => {
    const script = { id: 'script-id', type: 'OkScript', editorKind: 'builtin:ok-script' }

    expect(getUserCreatePath(script)).toBe('/scripts/script-id/users/add/ok-script')
    expect(getUserEditPath(script, { id: 'user-id' })).toBe(
      '/scripts/script-id/users/user-id/edit/ok-script'
    )
  })
})
