import { describe, expect, it } from 'vite-plus/test'
import { buildFieldPatch } from './fieldPatch'

describe('field patches', () => {
  it('writes only the requested group and preserves false and null values', () => {
    expect(buildFieldPatch('Info.Status', false)).toEqual({ Info: { Status: false } })
    expect(buildFieldPatch('IfEnabled', null)).toEqual({ IfEnabled: null })
  })
})
